"""构建编排骨架。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from shutil import which

from patchweaver.models.attempt import AttemptRecord
from patchweaver.models.rewrite import RewritePlan
from patchweaver.models.task import TaskContext


class BuildOrchestrator:
    """负责组织单轮构建尝试。"""

    def start_attempt(self, *, task_id: str, attempt_no: int) -> AttemptRecord:
        """生成一条占位 AttemptRecord。"""

        return AttemptRecord(
            task_id=task_id,
            attempt_no=attempt_no,
            attempt_id=f"{task_id}-A{attempt_no:03d}",
            status="created",
        )

    def execute_placeholder_build(
        self,
        *,
        task: TaskContext,
        attempt_no: int,
        plan: RewritePlan,
        rewritten_patch_path: Path,
        build_log_path: Path,
        build_command: str,
    ) -> tuple[AttemptRecord, str]:
        """执行一轮最小构建尝试。"""

        record = self.start_attempt(task_id=task.task_id, attempt_no=attempt_no)
        build_log_path.parent.mkdir(parents=True, exist_ok=True)

        command_path = which(build_command)
        if command_path is None:
            build_log = f"{build_command} 未找到，当前仅完成 MVP 骨架，未进入真实构建。"
            status = "failed"
            failure_type = "build_env_missing"
            module_path = None
        else:
            build_log = f"已找到构建命令 {command_path}，但当前版本仍使用占位构建流程。"
            status = "failed"
            failure_type = "build_not_implemented"
            module_path = None

        build_log_path.write_text(build_log + "\n", encoding="utf-8")
        return (
            record.model_copy(
                update={
                    "candidate_id": plan.candidate_ids[0] if plan.candidate_ids else None,
                    "status": status,
                    "failure_type": failure_type,
                    "build_log_path": build_log_path,
                    "module_path": module_path,
                    "rewritten_patch_path": rewritten_patch_path,
                    "finished_at": datetime.now(timezone.utc),
                }
            ),
            build_log,
        )
