"""回放摘要整理。"""

from __future__ import annotations

from pathlib import Path

from patchweaver.models.attempt import AttemptRecord
from patchweaver.models.task import TaskContext


class ReplayHarness:
    """负责整理最近一轮任务回放信息。"""

    def build_summary(
        self,
        *,
        task: TaskContext,
        task_dir: Path,
        attempts: list[AttemptRecord],
        latest_trace: dict[str, object] | None,
        replay_comparison: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """根据最新 trace 和尝试轮生成回放摘要。"""

        latest_attempt = attempts[-1] if attempts else None
        stage_routes: dict[str, object] = {}
        dispatch_modes: dict[str, object] = {}
        if latest_trace:
            summary = latest_trace.get("summary") or {}
            extras = summary.get("extras") or {}
            stage_routes = extras.get("stage_routes") or {}
            dispatch_modes = extras.get("dispatch_modes") or {}

        replay_files: list[str] = []
        if latest_attempt is not None:
            latest_attempt_dir = task_dir / "attempts" / f"{latest_attempt.attempt_no:03d}"
            for candidate in [
                latest_attempt_dir / "prompt" / "rewrite_recipe_prompt_packet.json",
                latest_attempt_dir / "logs" / "failure_record.json",
                latest_attempt_dir / "trace" / "failover.jsonl",
                latest_attempt_dir / "trace" / "harness_trace.json",
                latest_attempt_dir / "attempt_state.json",
                latest_attempt_dir / "artifacts" / "validation_report.json",
            ]:
                if candidate.exists() and (candidate.suffix != ".jsonl" or candidate.stat().st_size > 0):
                    replay_files.append(str(candidate))

        report_path = task_dir / "reports" / "report.json"
        evaluation_summary_path = task_dir / "reports" / "evaluation_summary.json"
        return {
            "command": "replay",
            "task_id": task.task_id,
            "latest_attempt_id": latest_attempt.attempt_id if latest_attempt else None,
            "latest_attempt_status": latest_attempt.status if latest_attempt else None,
            "trace_path": latest_trace["trace_path"] if latest_trace else None,
            "report_path": str(report_path) if report_path.exists() else None,
            "evaluation_summary_path": str(evaluation_summary_path) if evaluation_summary_path.exists() else None,
            "stage_routes": stage_routes,
            "dispatch_modes": dispatch_modes,
            "replay_files": replay_files,
            "closure_paths": {
                "task_dir": str(task_dir),
                "report_json": str(report_path) if report_path.exists() else None,
                "evaluation_summary": str(evaluation_summary_path) if evaluation_summary_path.exists() else None,
                "latest_build_log": str(latest_attempt.build_log_path) if latest_attempt and latest_attempt.build_log_path else None,
            },
            "comparison": replay_comparison or {},
            "status": "ok",
        }
