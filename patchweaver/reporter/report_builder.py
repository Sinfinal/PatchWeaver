"""报告生成骨架。"""

from __future__ import annotations

from patchweaver.models.harness import ArtifactRef
from patchweaver.models.report import AttemptDigest, FinalReport
from patchweaver.models.task import TaskContext
from patchweaver.models.attempt import AttemptRecord


class ReportBuilder:
    """负责汇总任务结果并生成最终报告。"""

    def build_report(
        self,
        *,
        task: TaskContext,
        attempts: list[AttemptRecord],
        artifacts: list[ArtifactRef],
        explanations: list[str] | None = None,
    ) -> FinalReport:
        """根据任务、尝试和产物索引生成报告。"""

        return FinalReport(
            task_summary={
                "task_id": task.task_id,
                "cve_id": task.cve_id,
                "target_kernel": task.target_kernel,
            },
            attempt_digest=[
                AttemptDigest(
                    attempt_id=item.attempt_id,
                    attempt_no=item.attempt_no,
                    status=item.status,
                    failure_type=item.failure_type,
                )
                for item in attempts
            ],
            artifact_index=artifacts,
            final_status=task.status,
            explanations=explanations or [],
        )
