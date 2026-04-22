"""回放摘要整理"""

from __future__ import annotations

from pathlib import Path

from patchweaver.models.attempt import AttemptRecord
from patchweaver.models.task import TaskContext
from patchweaver.models.validation import ValidationReport
from patchweaver.utils.path_policy import to_project_relative


class ReplayHarness:
    """负责整理最近一轮任务回放信息"""

    def __init__(self, project_root: Path | None = None) -> None:
        """保存项目根目录，供路径输出使用"""

        self.project_root = project_root.resolve() if project_root is not None else None

    def build_summary(
        self,
        *,
        task: TaskContext,
        task_dir: Path,
        attempts: list[AttemptRecord],
        latest_trace: dict[str, object] | None,
        replay_comparison: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """根据最新 trace 和尝试轮生成回放摘要"""

        latest_attempt = attempts[-1] if attempts else None
        stage_routes: dict[str, object] = {}
        dispatch_modes: dict[str, object] = {}
        if latest_trace:
            summary = latest_trace.get("summary") or {}
            extras = summary.get("extras") or {}
            stage_routes = extras.get("stage_routes") or {}
            dispatch_modes = extras.get("dispatch_modes") or {}

        validation_report = None
        replay_files: list[str] = []
        success_replay_files: list[str] = []
        failure_replay_files: list[str] = []
        if latest_attempt is not None:
            latest_attempt_dir = task_dir / "attempts" / f"{latest_attempt.attempt_no:03d}"
            validation_report = self._load_validation_report(latest_attempt_dir / "artifacts" / "validation_report.json")

            success_candidates = [
                latest_attempt_dir / "trace" / "harness_trace.json",
                latest_attempt_dir / "rewrite" / "rewritten.patch",
                latest_attempt_dir / "logs" / "build.log",
                latest_attempt_dir / "artifacts" / "validation_report.json",
                latest_attempt_dir / "artifacts" / "validation_matrix.json",
                latest_attempt_dir / "logs" / "selftest.log",
                latest_attempt_dir / "logs" / "load.log",
                latest_attempt_dir / "logs" / "unload.log",
                latest_attempt_dir / "logs" / "smoke.log",
                latest_attempt_dir / "logs" / "regression.log",
            ]
            failure_candidates = [
                latest_attempt_dir / "prompt" / "rewrite_recipe_prompt_packet.json",
                latest_attempt_dir / "logs" / "failure_record.json",
                latest_attempt_dir / "trace" / "failover.jsonl",
                latest_attempt_dir / "trace" / "harness_trace.json",
                latest_attempt_dir / "attempt_state.json",
                latest_attempt_dir / "artifacts" / "validation_report.json",
            ]
            success_replay_files = self._existing_paths(success_candidates)
            failure_replay_files = self._existing_paths(failure_candidates)

            if latest_attempt.status == "built":
                replay_files = success_replay_files or failure_replay_files
            else:
                replay_files = failure_replay_files

        closure_summary = self._closure_summary(
            latest_attempt=latest_attempt,
            validation_report=validation_report,
            success_replay_files=success_replay_files,
            failure_replay_files=failure_replay_files,
        )

        report_path = task_dir / "reports" / "report.json"
        evaluation_summary_path = task_dir / "reports" / "evaluation_summary.json"
        return {
            "command": "replay",
            "task_id": task.task_id,
            "latest_attempt_id": latest_attempt.attempt_id if latest_attempt else None,
            "latest_attempt_status": latest_attempt.status if latest_attempt else None,
            "latest_failure_type": latest_attempt.failure_type if latest_attempt else None,
            "latest_build_exec_status": latest_attempt.build_exec_status if latest_attempt else None,
            "latest_target_state": latest_attempt.target_state if latest_attempt else None,
            "trace_path": latest_trace["trace_path"] if latest_trace else None,
            "report_path": self._path(report_path) if report_path.exists() else None,
            "evaluation_summary_path": self._path(evaluation_summary_path) if evaluation_summary_path.exists() else None,
            "stage_routes": stage_routes,
            "dispatch_modes": dispatch_modes,
            "replay_files": replay_files,
            "success_replay_files": success_replay_files,
            "failure_replay_files": failure_replay_files,
            "closure_type": closure_summary["closure_type"],
            "closure_status": closure_summary["closure_status"],
            "success_replay_ready": closure_summary["success_replay_ready"],
            "missing_success_evidence": closure_summary["missing_success_evidence"],
            "closure_paths": {
                "task_dir": self._path(task_dir),
                "report_json": self._path(report_path) if report_path.exists() else None,
                "evaluation_summary": self._path(evaluation_summary_path) if evaluation_summary_path.exists() else None,
                "latest_build_log": self._path(latest_attempt.build_log_path) if latest_attempt and latest_attempt.build_log_path else None,
                "latest_build_exec_status": latest_attempt.build_exec_status if latest_attempt else None,
                "latest_target_state": latest_attempt.target_state if latest_attempt else None,
                "validation_status": validation_report.status if validation_report is not None else None,
            },
            "comparison": replay_comparison or {},
            "status": "ok",
        }

    def _closure_summary(
        self,
        *,
        latest_attempt: AttemptRecord | None,
        validation_report: ValidationReport | None,
        success_replay_files: list[str],
        failure_replay_files: list[str],
    ) -> dict[str, object]:
        """判断当前回放属于哪类闭环"""

        if latest_attempt is None:
            return {
                "closure_type": "pending",
                "closure_status": "missing_attempt",
                "success_replay_ready": False,
                "missing_success_evidence": ["缺少尝试轮记录"],
            }

        missing_success_evidence: list[str] = []
        if latest_attempt.status == "built":
            if latest_attempt.build_exec_status != "executed":
                missing_success_evidence.append("最近一轮未形成真实构建执行记录")
            if latest_attempt.module_path is None:
                missing_success_evidence.append("缺少模块产物路径")
            if validation_report is None:
                missing_success_evidence.append("缺少 validation_report")
            elif validation_report.status != "passed":
                missing_success_evidence.append(f"验证结果尚未放行，当前状态为 {validation_report.status}")
            expected_success_files = {"rewritten.patch", "build.log", "validation_report.json", "validation_matrix.json"}
            existing_names = {Path(item).name for item in success_replay_files}
            for file_name in sorted(expected_success_files - existing_names):
                missing_success_evidence.append(f"缺少 {file_name}")

        success_replay_ready = latest_attempt.status == "built" and not missing_success_evidence
        if success_replay_ready:
            closure_type = "success"
            closure_status = "ready"
        elif latest_attempt.status == "built":
            closure_type = "success_pending"
            closure_status = "missing_success_evidence"
        elif failure_replay_files:
            closure_type = "failure"
            closure_status = "ready"
        else:
            closure_type = "partial"
            closure_status = "incomplete"

        return {
            "closure_type": closure_type,
            "closure_status": closure_status,
            "success_replay_ready": success_replay_ready,
            "missing_success_evidence": missing_success_evidence,
        }

    def _existing_paths(self, paths: list[Path]) -> list[str]:
        """收集当前目录下真实存在的回放文件"""

        results: list[str] = []
        for candidate in paths:
            if candidate.exists() and (candidate.suffix != ".jsonl" or candidate.stat().st_size > 0):
                relative = self._path(candidate)
                if relative:
                    results.append(relative)
        return results

    def _load_validation_report(self, path: Path) -> ValidationReport | None:
        """读取当前轮验证报告"""

        if not path.exists():
            return None
        try:
            return ValidationReport.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            # 回放阶段优先给出可读摘要，半成品验证文件按缺失处理
            return None

    def _path(self, value: Path | None) -> str | None:
        """把项目内路径转换成相对源码根目录表达"""

        return to_project_relative(self.project_root, value)
