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
        if "kpatch-build 未找到" in build_log:
            failure_type = "build_env_missing"
        elif "未接入真实构建" in build_log:
            failure_type = "build_not_implemented"
        return FailureRecord(
            task_id=task_id,
            attempt_id=attempt_id,
            stage_name="build",
            failure_type=failure_type,
            summary=build_log.strip().splitlines()[0] if build_log.strip() else "构建失败",
            evidence=build_log.strip().splitlines()[:3],
        )
