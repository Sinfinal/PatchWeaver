"""构建失败归因骨架"""

from __future__ import annotations

import re
from pathlib import Path

from patchweaver.models.attempt import FailureRecord
from unidiff import PatchSet


class FailureClassifier:
    """负责把构建失败整理为结构化归因"""

    def classify(self, *, task_id: str, attempt_id: str, stage_name: str, summary: str) -> FailureRecord:
        """生成一条最小失败记录"""

        return FailureRecord(
            task_id=task_id,
            attempt_id=attempt_id,
            stage_name=stage_name,
            failure_type="unknown",
            summary=summary,
        )

    def classify_build_log(
        self,
        *,
        task_id: str,
        attempt_id: str,
        build_log: str,
        build_exec_status: str | None = None,
        failure_type_hint: str | None = None,
        rewritten_patch_path: Path | None = None,
    ) -> FailureRecord:
        """根据构建日志给出简单归因"""

        failure_type = failure_type_hint or "compile_failed"
        lowered_log = build_log.lower()
        executed_build = build_exec_status == "executed"
        lines = self._relevant_lines(build_log=build_log, executed_build=executed_build)
        lowered_relevant = "\n".join(lines).lower()

        # 先按我们自己生成的中文摘要做一层归类
        # 这样即使底层命令行输出差异比较大，也能先稳住大类判断
        if "未找到构建命令" in build_log or "kpatch-build 未找到" in build_log:
            failure_type = "build_env_missing"
        elif "找不到可用的内核源码目录" in build_log:
            failure_type = "kernel_src_missing"
        elif "没有找到 .config" in build_log or "源码目录中没有找到 .config" in build_log:
            failure_type = "kernel_config_missing"
        elif "找不到可用的 vmlinux" in build_log or "vmlinux 文件" in build_log:
            failure_type = "vmlinux_missing"
        elif not executed_build and ("目标源码已包含该补丁" in build_log or "无需重复应用" in build_log):
            failure_type = "target_already_patched"
        elif not executed_build and "目标内核配置未启用补丁涉及源码" in build_log:
            failure_type = "feature_not_enabled"
        elif not executed_build and "补丁触达目标架构之外的源码" in build_log:
            failure_type = "target_arch_mismatch"
        elif not executed_build and "源码树缺少模块构建缓存" in build_log:
            failure_type = "build_cache_incomplete"
        elif not executed_build and "apply 级预检查未通过" in build_log:
            failure_type = "patch_apply_failed"
        elif not executed_build and "file failed to apply" in lowered_log:
            failure_type = "patch_apply_failed"
        elif not executed_build and "only garbage was found in the patch input" in lowered_log:
            failure_type = "patch_apply_failed"
        elif not executed_build and "no valid patches in input" in lowered_log:
            failure_type = "patch_apply_failed"
        elif not executed_build and ("patch does not apply" in lowered_log or "corrupt patch" in lowered_log):
            failure_type = "patch_apply_failed"
        elif not executed_build and ("can't find file to patch" in lowered_log or "patch failed" in lowered_log):
            failure_type = "patch_apply_failed"
        elif "unreconcilable difference" in lowered_relevant:
            failure_type = "kpatch_constraint"
        elif "fentry" in lowered_relevant or "init section" in lowered_relevant or "section mismatch" in lowered_relevant:
            failure_type = "kpatch_constraint"
        elif "unsupported section change" in lowered_relevant:
            failure_type = "kpatch_constraint"
        elif "unsupported" in lowered_relevant and "kpatch" in lowered_relevant:
            failure_type = "kpatch_constraint"
        elif "command not found" in lowered_relevant:
            failure_type = "build_env_missing"

        summary = self._pick_summary(lines=lines, failure_type=failure_type, executed_build=executed_build)

        evidence = lines[:3]
        if failure_type == "patch_apply_failed":
            # apply 类失败通常上下文很多
            # 这里只保留最像“根因提示”的几行，方便前端和报告直接展示
            evidence = [
                line
                for line in lines
                if "failed to apply" in line.lower()
                or "patch failed" in line.lower()
                or "only garbage was found" in line.lower()
                or "can't find file to patch" in line.lower()
                or "apply 级预检查未通过" in line
                or "patch does not apply" in line.lower()
                or "no valid patches in input" in line.lower()
            ][:3] or evidence
        elif failure_type == "target_already_patched":
            evidence = [
                line
                for line in lines
                if "目标源码已包含该补丁" in line or "无需重复应用" in line
            ][:3] or evidence
        elif failure_type == "feature_not_enabled":
            evidence = [
                line
                for line in lines
                if "目标内核配置未启用" in line or "跳过 kpatch-build" in line
            ][:3] or evidence
        elif failure_type == "target_arch_mismatch":
            evidence = [
                line
                for line in lines
                if "当前验证机内核架构" in line or "目标架构不匹配源码" in line or "changed objects" in line
            ][:3] or evidence
        elif failure_type == "build_cache_incomplete":
            evidence = [
                line
                for line in lines
                if "源码树缺少模块构建缓存" in line or "缺失文件" in line or "prepare-build-tree" in line
            ][:3] or evidence
        elif failure_type == "kpatch_constraint":
            evidence = [
                line
                for line in lines
                if "fentry" in line.lower()
                or "init section" in line.lower()
                or "section mismatch" in line.lower()
                or "unsupported section change" in line.lower()
                or "unsupported" in line.lower()
            ][:3] or evidence
        elif executed_build and failure_type in {"compile_failed", "build_env_missing"}:
            evidence = [
                line
                for line in lines
                if "构建命令超时" in line
                or "error" in line.lower()
                or "failed" in line.lower()
                or "kernelversion is not set" in line.lower()
                or "退出码" in line
            ][:3] or evidence

        diagnostic_details: dict[str, object] = {}
        if failure_type == "kpatch_constraint":
            diagnostic_details["kpatch_constraint"] = self._diagnose_kpatch_constraint(
                lines=lines,
                rewritten_patch_path=rewritten_patch_path,
            )
        elif failure_type == "patch_apply_failed":
            diagnostic_details["patch_apply"] = self._diagnose_patch_apply_failure(lines=lines)

        return FailureRecord(
            task_id=task_id,
            attempt_id=attempt_id,
            stage_name="build",
            failure_type=failure_type,
            summary=summary,
            evidence=evidence,
            diagnostic_details=diagnostic_details,
        )

    def _relevant_lines(self, *, build_log: str, executed_build: bool) -> list[str]:
        """抽取本轮真正需要参与归因的日志片段"""

        lines = [line.strip() for line in build_log.strip().splitlines() if line.strip()]
        if not executed_build:
            return lines

        try:
            command_index = lines.index("[local command]")
        except ValueError:
            return lines
        return lines[command_index + 1 :] or lines

    def _pick_summary(self, *, lines: list[str], failure_type: str, executed_build: bool) -> str:
        """从日志中挑一条最像最终失败原因的摘要"""

        if not lines:
            return "构建失败"

        if failure_type == "feature_not_enabled":
            for line in lines:
                if "目标内核配置未启用" in line:
                    return line

        if failure_type == "build_cache_incomplete":
            for line in lines:
                if "源码树缺少模块构建缓存" in line or "缺失文件" in line:
                    return line

        if failure_type == "target_arch_mismatch":
            for line in lines:
                if "补丁触达目标架构之外的源码" in line or "目标架构不匹配源码" in line:
                    return line

        if executed_build:
            if failure_type == "kpatch_constraint":
                for marker in [
                    "unsupported section change",
                    "unreconcilable difference",
                    "section mismatch",
                    "fentry",
                    "init section",
                ]:
                    for line in lines:
                        if marker in line.lower():
                            return line
            for marker in [
                "构建命令超时",
                "kpatch build failed",
                "error:",
                "failed",
                "退出码",
            ]:
                for line in lines:
                    if marker in line.lower() if marker.islower() else marker in line:
                        return line

        for line in lines:
            if "error" in line.lower() or "failed" in line.lower():
                return line
        return lines[0]

    def _diagnose_kpatch_constraint(
        self,
        *,
        lines: list[str],
        rewritten_patch_path: Path | None,
    ) -> dict[str, object]:
        """把 kpatch 后端约束定位到对象、源码和函数线索"""

        combined = "\n".join(lines)
        section_changes = self._parse_unsupported_section_changes(lines)
        patch_index = self._index_patch(rewritten_patch_path)
        for item in section_changes:
            source_matches = self._match_sources_for_object(
                object_file=str(item["object_file"]),
                patch_index=patch_index,
            )
            item["source_files"] = [match["source_file"] for match in source_matches]
            item["functions"] = list(
                dict.fromkeys(
                    function
                    for match in source_matches
                    for function in list(match.get("functions") or [])
                    if function
                )
            )

        constraint_kind = "kpatch_constraint"
        lowered = combined.lower()
        if section_changes:
            constraint_kind = "unsupported_section_change"
        elif ".rela.call_sites" in lowered:
            constraint_kind = "rela_call_sites"
        elif "fentry" in lowered:
            constraint_kind = "fentry_constraint"
        elif "init section" in lowered or "section mismatch" in lowered:
            constraint_kind = "section_mismatch"

        return {
            "constraint_kind": constraint_kind,
            "section_changes": section_changes,
            "patch_files": patch_index["files"],
            "trigger_reason": self._trigger_reason(constraint_kind),
        }

    def _parse_unsupported_section_changes(self, lines: list[str]) -> list[dict[str, object]]:
        """解析 unsupported section change 形式的后端约束"""

        matches: list[dict[str, object]] = []
        pattern = re.compile(
            r"(?P<object>[A-Za-z0-9_./+-]+\.o):\s*(?P<count>\d+)\s+unsupported section change\(s\)",
            re.IGNORECASE,
        )
        for line in lines:
            match = pattern.search(line)
            if not match:
                continue
            matches.append(
                {
                    "object_file": Path(match.group("object")).name,
                    "section_change_count": int(match.group("count")),
                    "raw_line": line,
                }
            )
        return matches

    def _index_patch(self, rewritten_patch_path: Path | None) -> dict[str, object]:
        """索引 rewritten.patch 中的文件和 hunk 函数上下文"""

        if rewritten_patch_path is None or not rewritten_patch_path.exists():
            return {"files": [], "by_stem": {}}

        files: list[dict[str, object]] = []
        by_stem: dict[str, list[dict[str, object]]] = {}
        patch_text = rewritten_patch_path.read_text(encoding="utf-8", errors="replace")
        try:
            with rewritten_patch_path.open("r", encoding="utf-8", errors="replace") as handle:
                patch_set = PatchSet(handle)
        except Exception:
            return self._fallback_index_patch_text(patch_text)

        for patched_file in patch_set:
            source_file = str(getattr(patched_file, "path", "") or "")
            if not source_file:
                continue
            functions = list(
                dict.fromkeys(
                    function
                    for hunk in patched_file
                    for function in [self._extract_hunk_function(str(getattr(hunk, "section_header", "") or ""))]
                    if function
                )
            )
            record = {
                "source_file": source_file,
                "object_stem": Path(source_file).stem,
                "functions": functions,
            }
            files.append(record)
            by_stem.setdefault(str(record["object_stem"]), []).append(record)
        if not files:
            return self._fallback_index_patch_text(patch_text)
        return {"files": files, "by_stem": by_stem}

    def _fallback_index_patch_text(self, patch_text: str) -> dict[str, object]:
        """在 patch 不完全规范时用文本规则提取最小索引"""

        files: list[dict[str, object]] = []
        current_file: str | None = None
        functions: list[str] = []
        for line in patch_text.replace("\r\n", "\n").replace("\r", "\n").splitlines():
            if line.startswith("diff --git "):
                if current_file:
                    self._append_patch_file_index(files, current_file, functions)
                parts = line.split()
                current_file = parts[3][2:] if len(parts) >= 4 and parts[3].startswith("b/") else None
                functions = []
                continue
            if line.startswith("+++ b/"):
                current_file = line.removeprefix("+++ b/").strip()
                continue
            if line.startswith("@@"):
                function = self._extract_hunk_function(self._hunk_header_tail(line))
                if function:
                    functions.append(function)
        if current_file:
            self._append_patch_file_index(files, current_file, functions)

        by_stem: dict[str, list[dict[str, object]]] = {}
        for record in files:
            by_stem.setdefault(str(record["object_stem"]), []).append(record)
        return {"files": files, "by_stem": by_stem}

    def _append_patch_file_index(self, files: list[dict[str, object]], source_file: str, functions: list[str]) -> None:
        """追加一个源码文件索引"""

        files.append(
            {
                "source_file": source_file,
                "object_stem": Path(source_file).stem,
                "functions": list(dict.fromkeys(functions)),
            }
        )

    def _hunk_header_tail(self, line: str) -> str:
        """抽取 hunk header 尾部上下文"""

        parts = line.split("@@")
        return parts[-1].strip() if len(parts) >= 3 else ""

    def _match_sources_for_object(self, *, object_file: str, patch_index: dict[str, object]) -> list[dict[str, object]]:
        """按对象文件名反查 patch 中的源码和函数"""

        object_stem = Path(object_file).stem
        by_stem = patch_index.get("by_stem")
        if isinstance(by_stem, dict):
            matches = by_stem.get(object_stem)
            if isinstance(matches, list) and matches:
                return [item for item in matches if isinstance(item, dict)]
        files = patch_index.get("files")
        if isinstance(files, list) and len(files) == 1 and isinstance(files[0], dict):
            return [files[0]]
        return []

    def _extract_hunk_function(self, section_header: str) -> str | None:
        """从 hunk header 的上下文里抽取函数名线索"""

        header = section_header.strip()
        if not header:
            return None
        match = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", header)
        if not match:
            return header[:120]
        name = match.group(1)
        if name in {"if", "for", "while", "switch", "return", "sizeof"}:
            return header[:120]
        return name

    def _trigger_reason(self, constraint_kind: str) -> str:
        """生成可直接展示给 Agent 和报告的约束解释"""

        if constraint_kind == "unsupported_section_change":
            return "kpatch-build 检测到目标对象文件 section 变化超出热补丁后端可接受范围"
        if constraint_kind == "rela_call_sites":
            return "补丁触发 .rela.call_sites 相关重定位变化，当前 kpatch 后端无法安全合成 livepatch"
        if constraint_kind == "fentry_constraint":
            return "目标函数缺少可用 fentry 或 fentry 约束未满足"
        if constraint_kind == "section_mismatch":
            return "补丁涉及 init/exit 或其他 section 语义不匹配路径"
        return "构建日志命中 kpatch 后端约束，需要收缩改写范围或判定不可热补丁化"

    def _diagnose_patch_apply_failure(self, *, lines: list[str]) -> dict[str, object]:
        """把 patch apply 失败拆成源码状态和冲突线索"""

        combined = "\n".join(lines)
        lowered = combined.lower()
        conflict_files = self._parse_apply_conflict_files(lines)
        source_state = self._parse_source_state(lines)
        if "can't find file to patch" in lowered or "no such file" in lowered:
            subtype = "missing_file"
            reason = "patch 触达文件在当前源码树中不存在"
        elif "only garbage was found" in lowered or "no valid patches in input" in lowered or "corrupt patch" in lowered:
            subtype = "invalid_patch_format"
            reason = "patch 文件格式异常，无法进入源码状态判断"
        elif source_state == "likely_patched":
            subtype = "source_too_new_or_already_patched"
            reason = "当前源码树疑似已包含修复或版本过新，优先尝试 reverse-unpatch"
        elif "patch failed" in lowered or "patch does not apply" in lowered or "hunk" in lowered:
            subtype = "context_mismatch"
            reason = "patch 上下文与当前源码树不一致，需要检查 stable commit 或目标源码状态"
        else:
            subtype = "unknown_apply_failure"
            reason = "apply 失败证据不足，需要查看完整 precheck stderr"
        return {
            "subtype": subtype,
            "source_state": source_state,
            "conflict_files": conflict_files,
            "conflict_hunks": self._parse_apply_conflict_hunks(lines),
            "reverse_unpatch_recommended": subtype in {"source_too_new_or_already_patched", "context_mismatch"},
            "stable_source_alignment_required": subtype in {"context_mismatch", "missing_file"},
            "reason": reason,
        }

    def _parse_apply_conflict_files(self, lines: list[str]) -> list[str]:
        """从 git apply 输出里提取冲突文件"""

        files: list[str] = []
        patterns = [
            re.compile(r"Checking patch (?P<file>[^.].*?)\.\.\."),
            re.compile(r"error:\s+patch failed:\s+(?P<file>[^:]+):\d+"),
            re.compile(r"error:\s+(?P<file>[^:]+):\s+patch does not apply"),
        ]
        for line in lines:
            for pattern in patterns:
                match = pattern.search(line)
                if not match:
                    continue
                files.append(match.group("file").strip())
        return list(dict.fromkeys(files))

    def _parse_apply_conflict_hunks(self, lines: list[str]) -> list[dict[str, object]]:
        """提取失败 hunk 的文件和行号"""

        hunks: list[dict[str, object]] = []
        pattern = re.compile(r"error:\s+patch failed:\s+(?P<file>[^:]+):(?P<line>\d+)")
        for line in lines:
            match = pattern.search(line)
            if match:
                hunks.append({"file": match.group("file"), "line": int(match.group("line"))})
        return hunks[:20]

    def _parse_source_state(self, lines: list[str]) -> str | None:
        """读取构建日志中的源码状态提示"""

        for line in lines:
            if "源码期望状态:" in line:
                return line.split("源码期望状态:", 1)[-1].strip() or None
            if "目标态结论:" in line:
                return line.split("目标态结论:", 1)[-1].strip() or None
        return None
