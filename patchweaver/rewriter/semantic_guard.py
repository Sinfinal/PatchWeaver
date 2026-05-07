"""semantic guard 改写执行器"""

from __future__ import annotations

import re
from typing import Any

from patchweaver.models.semantic import RepairIntent


class SemanticGuardRewriter:
    """从官方 patch 中提取函数局部 guard hunk"""

    def rewrite(
        self,
        *,
        patch_text: str,
        repair_intent: RepairIntent | None,
        force: bool = False,
    ) -> tuple[str, dict[str, Any]]:
        """返回 guard 优先的 rewritten patch"""

        if repair_intent is None:
            return patch_text, self._report("skipped", False, "缺少 RepairIntent，保留原始 patch", [], [])
        if repair_intent.recommended_strategy != "semantic_guard" and not force:
            return patch_text, self._report(
                "skipped",
                False,
                f"RepairIntent 推荐 {repair_intent.recommended_strategy}，不执行 semantic guard 收缩",
                [],
                [],
            )

        sections = self._split_diff_sections(patch_text)
        if not sections:
            return patch_text, self._report("skipped", False, "未识别到 diff section，保留原始 patch", [], [])

        kept_sections: list[str] = []
        kept_reasons: list[str] = []
        dropped_reasons: list[str] = []
        transformations: list[str] = []
        for section in sections:
            headers, hunks = self._split_hunks(section)
            selected: list[str] = []
            for hunk in hunks:
                rewritten_hunk, hunk_transformations = self._rewrite_call_sensitive_guard(
                    hunk=hunk,
                    repair_intent=repair_intent,
                )
                transformations.extend(hunk_transformations)
                decision, reason = self._decide_hunk(rewritten_hunk)
                if decision == "keep":
                    selected.append(rewritten_hunk)
                    kept_reasons.append(reason)
                else:
                    dropped_reasons.append(reason)
            if selected:
                kept_sections.append("".join(headers + selected))

        if not kept_sections:
            return patch_text, self._report(
                "no_guard_candidate",
                False,
                "没有识别到可独立保留的函数局部 guard hunk，保留原始 patch",
                kept_reasons,
                dropped_reasons,
                transformations,
            )

        rewritten = "\n".join(item.rstrip("\n") for item in kept_sections)
        if not rewritten.endswith("\n"):
            rewritten += "\n"
        effective = self._normalized_changed_lines(rewritten) != self._normalized_changed_lines(patch_text)
        status = "applied" if effective else "pass_through"
        summary = (
            "已收缩为函数局部 semantic guard hunk"
            if effective
            else "原始 patch 已基本符合 semantic guard 形态"
        )
        return rewritten, self._report(status, effective, summary, kept_reasons, dropped_reasons, transformations)

    def _rewrite_call_sensitive_guard(
        self,
        *,
        hunk: str,
        repair_intent: RepairIntent,
    ) -> tuple[str, list[str]]:
        """把 guard 中容易触发 call_sites 变化的表达式收缩成函数内判断"""

        preserve_warn = any(
            "WARN_ON" in effect or "warning" in effect.lower()
            for effect in repair_intent.preserved_side_effects
        )
        lines: list[str] = []
        transformations: list[str] = []
        for line in hunk.splitlines(keepends=True):
            if not line.startswith("+") or line.startswith("+++"):
                lines.append(line)
                continue

            body = line[1:]
            newline = "\n" if body.endswith("\n") else ""
            rewritten_body, line_transformations = self._rewrite_added_guard_line(
                body=body.rstrip("\n"),
                preserve_warn=preserve_warn,
            )
            lines.append("+" + rewritten_body + newline)
            transformations.extend(line_transformations)
        return "".join(lines), transformations

    def _rewrite_added_guard_line(self, *, body: str, preserve_warn: bool) -> tuple[str, list[str]]:
        """改写单条新增 guard 行"""

        rewritten = body
        transformations: list[str] = []
        if not preserve_warn:
            warn_rewritten = self._rewrite_warn_guard(rewritten)
            if warn_rewritten != rewritten:
                transformations.append("WARN_ON guard -> unlikely guard")
                rewritten = warn_rewritten

        helper_rewritten = self._rewrite_zero_helper_guard(rewritten)
        if helper_rewritten != rewritten:
            transformations.append("helper zero guard -> direct field zero guard")
            rewritten = helper_rewritten
        return rewritten, transformations

    def _rewrite_warn_guard(self, line: str) -> str:
        """去掉 guard 条件中的诊断宏调用，降低 call_sites 变化概率"""

        pattern = re.compile(
            r"\b(?:WARN_ON_ONCE|WARN_ON|VM_WARN_ON_ONCE|VM_WARN_ON)\s*"
            r"\((?P<expr>[^()]*(?:\([^()]*\)[^()]*)?)\)"
        )
        return pattern.sub(lambda match: f"unlikely({match.group('expr').strip()})", line)

    def _rewrite_zero_helper_guard(self, line: str) -> str:
        """把零值 helper guard 收缩成直接字段判断"""

        rewritten = re.sub(
            r"btrfs_root_refs\s*\(\s*&(?P<root>[A-Za-z_][A-Za-z0-9_]*)->root_item\s*\)\s*==\s*0",
            lambda match: f"!{match.group('root')}->root_item.refs",
            line,
        )
        rewritten = re.sub(
            r"!\s*btrfs_root_refs\s*\(\s*&(?P<root>[A-Za-z_][A-Za-z0-9_]*)->root_item\s*\)",
            lambda match: f"!{match.group('root')}->root_item.refs",
            rewritten,
        )
        rewritten = re.sub(
            r"btrfs_root_refs\s*\(\s*&(?P<root>[A-Za-z_][A-Za-z0-9_]*)->root_item\s*\)\s*!=\s*0",
            lambda match: f"{match.group('root')}->root_item.refs",
            rewritten,
        )
        return rewritten

    def _decide_hunk(self, hunk: str) -> tuple[str, str]:
        """判断一个 hunk 是否可作为 semantic guard 保留"""

        header = hunk.splitlines()[0] if hunk.splitlines() else ""
        context = self._hunk_context(header)
        added_lines = [
            line[1:].strip()
            for line in hunk.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        ]
        removed_lines = [
            line[1:].strip()
            for line in hunk.splitlines()
            if line.startswith("-") and not line.startswith("---")
        ]
        changed_lines = added_lines + removed_lines
        if any(self._is_state_or_section_change(line) for line in changed_lines):
            return "drop", f"{context or '<unknown>'}: 触达状态、结构或 section 生命周期，非局部 guard"
        if self._looks_guard_hunk(added_lines):
            return "keep", f"{context or '<unknown>'}: 新增函数局部 guard"
        return "drop", f"{context or '<unknown>'}: 未识别到 guard 条件和安全退出"

    def _looks_guard_hunk(self, added_lines: list[str]) -> bool:
        """识别新增条件保护和退出路径"""

        joined = "\n".join(added_lines)
        has_condition = any(re.search(r"\bif\s*\(", line) for line in added_lines)
        has_safe_exit = any(
            re.search(r"\breturn\b|\bgoto\b", line) or line in {"break;", "continue;"}
            for line in added_lines
        )
        has_guarded_side_effect = any(self._looks_side_effect(line) for line in added_lines)
        has_guard_hint = any(
            token in joined.lower()
            for token in [
                "null",
                "size",
                "len",
                "overflow",
                "invalid",
                "-einval",
                "-enomem",
                "-efault",
                "page_size",
                "unlikely",
                "free_",
            ]
        )
        return has_condition and (has_safe_exit or has_guarded_side_effect or has_guard_hint)

    def _looks_side_effect(self, line: str) -> bool:
        """识别 guard 分支内必须保留的调用或赋值"""

        stripped = line.strip()
        if not stripped or stripped.startswith(("/*", "*", "//", "if ", "if(")):
            return False
        if re.search(r"\breturn\b|\bgoto\b", stripped) or stripped in {"break;", "continue;", "{", "}"}:
            return False
        return bool(re.search(r"\w+\s*\(", stripped) or re.search(r"(?<![=!<>])=(?!=)", stripped))

    def _is_state_or_section_change(self, line: str) -> bool:
        """识别不适合 semantic guard 直接表达的改动"""

        stripped = line.strip()
        lowered = stripped.lower()
        if re.match(r"^(typedef\s+)?(struct|enum|union)\s+\w+", stripped):
            return True
        if re.match(r"^static\s+(?!inline\b).*(=|;|\[)", stripped):
            return True
        return any(token in lowered for token in ["__init", "__exit", "module_", "export_symbol", "module_device_table"])

    def _split_diff_sections(self, patch_text: str) -> list[str]:
        """按 diff --git 切分文件 section"""

        normalized = patch_text.replace("\r\n", "\n").replace("\r", "\n")
        starts = [match.start() for match in re.finditer(r"(?m)^diff --git ", normalized)]
        if not starts:
            return []
        return [
            normalized[start : starts[index + 1] if index + 1 < len(starts) else len(normalized)]
            for index, start in enumerate(starts)
        ]

    def _split_hunks(self, section: str) -> tuple[list[str], list[str]]:
        """把文件 section 拆成 header 和 hunk 列表"""

        lines = section.splitlines(keepends=True)
        hunk_starts = [index for index, line in enumerate(lines) if line.startswith("@@")]
        if not hunk_starts:
            return lines, []
        headers = lines[: hunk_starts[0]]
        hunks: list[str] = []
        for index, start in enumerate(hunk_starts):
            end = hunk_starts[index + 1] if index + 1 < len(hunk_starts) else len(lines)
            hunks.append("".join(lines[start:end]))
        return headers, hunks

    def _hunk_context(self, hunk_header: str) -> str:
        """抽取 hunk header 尾部上下文"""

        parts = hunk_header.split("@@")
        return parts[-1].strip() if len(parts) >= 3 else ""

    def _normalized_changed_lines(self, patch_text: str) -> list[str]:
        """只比较变更行，避免 header 细节影响 effective 判断"""

        lines: list[str] = []
        for line in patch_text.splitlines():
            if line.startswith(("+++", "---")):
                continue
            if line.startswith(("+", "-")):
                lines.append(line.strip())
        return lines

    def _report(
        self,
        status: str,
        effective: bool,
        summary: str,
        kept_hunks: list[str],
        dropped_hunks: list[str],
        transformations: list[str] | None = None,
    ) -> dict[str, Any]:
        """生成改写报告"""

        transformations = list(dict.fromkeys(transformations or []))
        return {
            "strategy": "semantic_guard_rewrite",
            "status": status,
            "effective": effective,
            "summary": summary,
            "kept_hunk_count": len(kept_hunks),
            "dropped_hunk_count": len(dropped_hunks),
            "call_elision_count": len(transformations),
            "transformations": transformations[:20],
            "kept_hunks": kept_hunks[:20],
            "dropped_hunks": dropped_hunks[:20],
        }
