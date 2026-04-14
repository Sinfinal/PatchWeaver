"""阶段评测汇总。"""

from __future__ import annotations

from patchweaver.models.attempt import AttemptRecord
from patchweaver.models.harness import ArtifactRef


class Evaluator:
    """负责基于尝试轮和产物索引输出阶段统计。"""

    def summarize(self, *, attempts: list[AttemptRecord], artifacts: list[ArtifactRef]) -> dict[str, object]:
        """生成最小评测摘要。"""

        total_attempts = len(attempts)
        built_attempts = sum(1 for item in attempts if item.status == "built")
        failed_attempts = sum(1 for item in attempts if item.status == "failed")
        average_attempt_no = (sum(item.attempt_no for item in attempts) / total_attempts) if attempts else 0.0

        failure_breakdown: dict[str, int] = {}
        for item in attempts:
            if not item.failure_type:
                continue
            failure_breakdown[item.failure_type] = failure_breakdown.get(item.failure_type, 0) + 1

        artifact_types: dict[str, int] = {}
        for artifact in artifacts:
            artifact_types[artifact.artifact_type] = artifact_types.get(artifact.artifact_type, 0) + 1

        return {
            "total_attempts": total_attempts,
            "built_attempts": built_attempts,
            "failed_attempts": failed_attempts,
            "success_rate": (built_attempts / total_attempts) if total_attempts else 0.0,
            "average_attempt_no": average_attempt_no,
            "failure_breakdown": failure_breakdown,
            "artifact_type_counts": artifact_types,
        }
