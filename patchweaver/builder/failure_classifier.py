"""构建失败归因骨架。"""

from __future__ import annotations

from patchweaver.models.attempt import FailureRecord


class FailureClassifier:
    """负责把构建失败整理为结构化归因。"""

    def classify(self, *, task_id: str, attempt_id: str, stage_name: str, summary: str) -> FailureRecord:
        """生成一条最小失败记录。"""

        return FailureRecord(
            task_id=task_id,
            attempt_id=attempt_id,
            stage_name=stage_name,
            failure_type="unknown",
            summary=summary,
        )

    def classify_build_log(self, *, task_id: str, attempt_id: str, build_log: str) -> FailureRecord:
        """根据构建日志给出简单归因。"""

        failure_type = "compile_failed"
        lowered_log = build_log.lower()

        if "未找到构建命令" in build_log or "kpatch-build 未找到" in build_log:
            failure_type = "build_env_missing"
        elif "找不到可用的内核源码目录" in build_log:
            failure_type = "kernel_src_missing"
        elif "没有找到 .config" in build_log or "源码目录中没有找到 .config" in build_log:
            failure_type = "kernel_config_missing"
        elif "找不到可用的 vmlinux" in build_log or "vmlinux 文件" in build_log:
            failure_type = "vmlinux_missing"
        elif "目标源码已包含该补丁" in build_log or "无需重复应用" in build_log:
            failure_type = "target_already_patched"
        elif "apply 级预检查未通过" in build_log:
            failure_type = "patch_apply_failed"
        elif "file failed to apply" in lowered_log:
            failure_type = "patch_apply_failed"
        elif "only garbage was found in the patch input" in lowered_log:
            failure_type = "patch_apply_failed"
        elif "no valid patches in input" in lowered_log:
            failure_type = "patch_apply_failed"
        elif "patch does not apply" in lowered_log or "corrupt patch" in lowered_log:
            failure_type = "patch_apply_failed"
        elif "can't find file to patch" in lowered_log or "patch failed" in lowered_log:
            failure_type = "patch_apply_failed"
        elif "unreconcilable difference" in lowered_log:
            failure_type = "kpatch_constraint"
        elif "fentry" in lowered_log or "init section" in lowered_log or "section mismatch" in lowered_log:
            failure_type = "kpatch_constraint"
        elif "unsupported" in lowered_log and "kpatch" in lowered_log:
            failure_type = "kpatch_constraint"
        elif "command not found" in lowered_log:
            failure_type = "build_env_missing"

        lines = [line.strip() for line in build_log.strip().splitlines() if line.strip()]
        summary = "构建失败"
        for line in lines:
            if "error" in line.lower() or "failed" in line.lower():
                summary = line
                break
        else:
            if lines:
                summary = lines[0]

        evidence = lines[:3]
        if failure_type == "patch_apply_failed":
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

        return FailureRecord(
            task_id=task_id,
            attempt_id=attempt_id,
            stage_name="build",
            failure_type=failure_type,
            summary=summary,
            evidence=evidence,
        )
