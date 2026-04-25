"""构建失败归因骨架"""

from __future__ import annotations

from patchweaver.models.attempt import FailureRecord


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
        elif failure_type == "kpatch_constraint":
            evidence = [
                line
                for line in lines
                if "fentry" in line.lower()
                or "init section" in line.lower()
                or "section mismatch" in line.lower()
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

        return FailureRecord(
            task_id=task_id,
            attempt_id=attempt_id,
            stage_name="build",
            failure_type=failure_type,
            summary=summary,
            evidence=evidence,
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

        if executed_build:
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
