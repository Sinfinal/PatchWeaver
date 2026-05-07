"""section change 专项收缩改写"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class HunkDecision:
    """记录 hunk 初判与依赖关系"""

    hunk: str
    context: str
    decision: str
    reason: str
    changed_lines: list[str]
    defined_identifiers: set[str] = field(default_factory=set)
    referenced_identifiers: set[str] = field(default_factory=set)
    kept_by_dependency: list[str] = field(default_factory=list)


class SectionChangeAvoidance:
    """针对 kpatch section change 约束收缩 patch 编辑半径"""

    def rewrite(self, patch_text: str) -> tuple[str, dict[str, Any]]:
        """过滤高风险 hunk，并尽量保留函数局部修复依赖"""

        sections = self._split_diff_sections(patch_text)
        if not sections:
            return patch_text, self._report(False, "未识别到 diff section，保留原始 patch", [], [])

        kept_sections: list[str] = []
        kept_hunks: list[str] = []
        dropped_hunks: list[str] = []
        kept_dependencies: list[str] = []
        dropped_dependencies: list[str] = []
        unresolved_dependencies: list[str] = []
        for section in sections:
            headers, hunks = self._split_hunks(section)
            decisions = [self._hunk_decision(hunk) for hunk in hunks]
            self._preserve_required_dependencies(decisions)
            selected: list[str] = []
            for item in decisions:
                if item.decision == "keep":
                    selected.append(item.hunk)
                    kept_hunks.append(item.reason)
                    kept_dependencies.extend(item.kept_by_dependency)
                else:
                    dropped_hunks.append(item.reason)
                    dropped_dependencies.extend(sorted(item.defined_identifiers))
            unresolved_dependencies.extend(self._unresolved_dependencies(decisions))
            if selected:
                kept_sections.append("".join(headers + selected))

        if not kept_sections:
            return patch_text, self._report(
                False,
                "没有找到可安全保留的函数局部 hunk，保留原始 patch",
                kept_hunks,
                dropped_hunks,
                kept_dependencies,
                dropped_dependencies,
                unresolved_dependencies,
            )

        # unified diff 中单独一个空格表示空白上下文行，不能被 rstrip() 当成普通尾部空白删掉
        rewritten = "\n".join(item.rstrip("\n") for item in kept_sections)
        if not rewritten.endswith("\n"):
            rewritten += "\n"
        changed = self._normalized_changed_lines(rewritten) != self._normalized_changed_lines(patch_text)
        return rewritten, self._report(
            changed,
            "已移除可能触发 section change 的全局或初始化类 hunk" if changed else "收缩策略未改变 patch",
            kept_hunks,
            dropped_hunks,
            kept_dependencies,
            dropped_dependencies,
            unresolved_dependencies,
        )

    def _report(
        self,
        effective: bool,
        summary: str,
        kept_hunks: list[str],
        dropped_hunks: list[str],
        kept_dependencies: list[str] | None = None,
        dropped_dependencies: list[str] | None = None,
        unresolved_dependencies: list[str] | None = None,
    ) -> dict[str, Any]:
        """整理策略执行摘要"""

        kept_dependencies = list(dict.fromkeys(kept_dependencies or []))
        dropped_dependencies = list(dict.fromkeys(dropped_dependencies or []))
        unresolved_dependencies = list(dict.fromkeys(unresolved_dependencies or []))
        return {
            "strategy": "section_change_avoidance_rewrite",
            "effective": effective,
            "summary": summary,
            "kept_hunk_count": len(kept_hunks),
            "dropped_hunk_count": len(dropped_hunks),
            "kept_hunks": kept_hunks[:20],
            "dropped_hunks": dropped_hunks[:20],
            "kept_dependencies": kept_dependencies[:20],
            "dropped_dependencies": dropped_dependencies[:20],
            "unresolved_dependencies": unresolved_dependencies[:20],
            "dependency_gap": bool(unresolved_dependencies),
        }

    def _split_diff_sections(self, patch_text: str) -> list[str]:
        """按 diff --git 切分文件级 section"""

        normalized = patch_text.replace("\r\n", "\n").replace("\r", "\n")
        starts = [match.start() for match in re.finditer(r"(?m)^diff --git ", normalized)]
        if not starts:
            return []
        sections: list[str] = []
        for index, start in enumerate(starts):
            end = starts[index + 1] if index + 1 < len(starts) else len(normalized)
            sections.append(normalized[start:end])
        return sections

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

    def _hunk_decision(self, hunk: str) -> HunkDecision:
        """判断 hunk 是否适合在 section change 收缩路线中保留"""

        first_line = hunk.splitlines()[0] if hunk.splitlines() else ""
        context = self._hunk_context(first_line)
        changed_lines = [
            line[1:].strip()
            for line in hunk.splitlines()
            if (line.startswith("+") or line.startswith("-")) and not line.startswith("+++") and not line.startswith("---")
        ]
        defined_identifiers = self._defined_identifiers(changed_lines)
        referenced_identifiers = self._referenced_identifiers(hunk)
        if any(self._is_high_risk_changed_line(line) for line in changed_lines):
            return HunkDecision(
                hunk=hunk,
                context=context,
                decision="drop",
                reason=f"{context or '<unknown>'}: 全局符号、初始化或 section 相关改动风险较高",
                changed_lines=changed_lines,
                defined_identifiers=defined_identifiers,
                referenced_identifiers=referenced_identifiers,
            )
        if self._looks_function_local(context):
            return HunkDecision(
                hunk=hunk,
                context=context,
                decision="keep",
                reason=f"{context}: 函数局部 hunk",
                changed_lines=changed_lines,
                defined_identifiers=defined_identifiers,
                referenced_identifiers=referenced_identifiers,
            )
        if changed_lines and all(self._looks_statement_like(line) for line in changed_lines):
            return HunkDecision(
                hunk=hunk,
                context=context,
                decision="keep",
                reason=f"{context or '<unknown>'}: 语句级改动",
                changed_lines=changed_lines,
                defined_identifiers=defined_identifiers,
                referenced_identifiers=referenced_identifiers,
            )
        return HunkDecision(
            hunk=hunk,
            context=context,
            decision="drop",
            reason=f"{context or '<unknown>'}: 缺少函数局部上下文",
            changed_lines=changed_lines,
            defined_identifiers=defined_identifiers,
            referenced_identifiers=referenced_identifiers,
        )

    def _preserve_required_dependencies(self, decisions: list[HunkDecision]) -> None:
        """把被保留 hunk 依赖的定义一起保住"""

        while True:
            kept_refs = set().union(*(item.referenced_identifiers for item in decisions if item.decision == "keep"))
            changed = False
            for item in decisions:
                if item.decision != "drop" or not item.defined_identifiers:
                    continue
                required = sorted(item.defined_identifiers & kept_refs)
                if not required:
                    continue
                item.decision = "keep"
                item.kept_by_dependency = required
                item.reason = f"{item.context or '<unknown>'}: 依赖保持，保留被函数局部 hunk 引用的定义 {', '.join(required)}"
                changed = True
            if not changed:
                return

    def _unresolved_dependencies(self, decisions: list[HunkDecision]) -> list[str]:
        """列出被保留 hunk 仍引用但已被删除的定义"""

        kept_refs = set().union(*(item.referenced_identifiers for item in decisions if item.decision == "keep"))
        dropped_defs = set().union(*(item.defined_identifiers for item in decisions if item.decision == "drop"))
        return sorted(kept_refs & dropped_defs)

    def _hunk_context(self, hunk_header: str) -> str:
        """抽取 hunk header 的尾部上下文"""

        parts = hunk_header.split("@@")
        if len(parts) < 3:
            return ""
        return parts[-1].strip()

    def _looks_function_local(self, context: str) -> bool:
        """识别函数上下文"""

        if not context or "(" not in context or ")" not in context:
            return False
        lowered = context.strip().lower()
        blocked_prefixes = ("struct ", "enum ", "union ", "typedef ", "#define", "static const struct")
        return not lowered.startswith(blocked_prefixes)

    def _looks_statement_like(self, line: str) -> bool:
        """判断变更行是否更像函数体内语句"""

        stripped = line.strip()
        if not stripped:
            return False
        if self._is_high_risk_changed_line(stripped):
            return False
        return stripped.endswith(";") or stripped.endswith("{") or stripped.endswith("}") or "return " in stripped

    def _is_high_risk_changed_line(self, line: str) -> bool:
        """识别容易触发 section 或全局对象变化的改动"""

        stripped = line.strip()
        lowered = stripped.lower()
        if not stripped:
            return False
        high_risk_markers = [
            "export_symbol",
            "module_",
            "__init",
            "__exit",
            "define_",
            "declare_",
            "module_device_table",
            "obj-",
        ]
        if any(marker in lowered for marker in high_risk_markers):
            return True
        if stripped.startswith(("#define", "#include", "MODULE_", "EXPORT_SYMBOL")):
            return True
        if re.match(r"^(static\s+)?(const\s+)?struct\s+\w+\s+\w+\s*(=|\[)", stripped):
            return True
        if re.match(r"^static\s+(?!.*\().*[A-Za-z_][A-Za-z0-9_]*\s*(=|;|\[)", stripped):
            return True
        if stripped.startswith(".") and "=" in stripped:
            return True
        return False

    def _defined_identifiers(self, changed_lines: list[str]) -> set[str]:
        """抽取 hunk 中新定义或被改动定义的标识符"""

        identifiers: set[str] = set()
        for line in changed_lines:
            stripped = line.strip()
            if not stripped:
                continue
            define_match = re.match(r"#\s*define\s+([A-Za-z_][A-Za-z0-9_]*)", stripped)
            if define_match:
                identifiers.add(define_match.group(1))
                continue
            function_match = re.match(
                r"(?:static\s+)?(?:inline\s+)?(?:const\s+)?[A-Za-z_][A-Za-z0-9_\s\*]+\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
                stripped,
            )
            if function_match and not stripped.endswith(";"):
                identifiers.add(function_match.group(1))
                continue
            object_match = re.match(
                r"(?:static\s+)?(?:const\s+)?(?:struct\s+\w+\s+|enum\s+\w+\s+|union\s+\w+\s+)?[A-Za-z_][A-Za-z0-9_\s\*]*\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\[|=|;)",
                stripped,
            )
            if object_match:
                identifiers.add(object_match.group(1))
        return identifiers

    def _referenced_identifiers(self, hunk: str) -> set[str]:
        """抽取 hunk 内引用到的标识符"""

        ignored = {
            "if",
            "else",
            "for",
            "while",
            "switch",
            "case",
            "return",
            "sizeof",
            "static",
            "const",
            "struct",
            "enum",
            "union",
            "int",
            "long",
            "unsigned",
            "signed",
            "void",
            "char",
            "bool",
            "true",
            "false",
            "NULL",
        }
        identifiers: set[str] = set()
        for line in hunk.splitlines():
            if line.startswith(("diff --git", "---", "+++", "@@")):
                continue
            for identifier in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", line):
                if identifier not in ignored:
                    identifiers.add(identifier)
        return identifiers

    def _normalized_changed_lines(self, patch_text: str) -> list[str]:
        """抽取变更行用于判断策略是否实际改变 patch"""

        return [
            line.strip()
            for line in patch_text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
            if (line.startswith("+") or line.startswith("-")) and not line.startswith("+++") and not line.startswith("---")
        ]
