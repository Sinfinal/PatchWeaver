"""任务查询与动作执行服务。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from patchweaver.api.deps import ApiContext
from patchweaver.config.resolver import resolve_runtime
from patchweaver.harness.attempt_engine import AttemptEngine
from patchweaver.harness.workspace_guard import WorkspaceGuard
from patchweaver.models.task import TaskContext
from patchweaver.storage.sqlite import connect_sqlite


class TaskQueryService:
    """负责任务列表、详情和动作入口。"""

    def __init__(self, context: ApiContext) -> None:
        """保存 API 共享上下文。"""

        self.context = context

    def list_tasks(
        self,
        *,
        limit: int = 50,
        cve_id: str | None = None,
        status: str | None = None,
        failure_type: str | None = None,
        target_kernel: str | None = None,
    ) -> dict[str, Any]:
        """按筛选条件读取任务列表。"""

        conditions: list[str] = []
        parameters: list[Any] = []
        if cve_id:
            conditions.append("t.cve_id LIKE ?")
            parameters.append(f"%{cve_id}%")
        if status:
            conditions.append("t.status = ?")
            parameters.append(status)
        if target_kernel:
            conditions.append("t.target_kernel = ?")
            parameters.append(target_kernel)
        if failure_type:
            conditions.append(
                """
                EXISTS (
                    SELECT 1
                    FROM failure_records fr
                    WHERE fr.task_ref = t.task_id AND fr.failure_type = ?
                )
                """
            )
            parameters.append(failure_type)

        where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"""
        SELECT t.task_id, t.cve_id, t.target_kernel, t.status, t.current_attempt, t.max_attempts,
               t.workspace_dir, t.created_at, t.updated_at,
               (
                   SELECT fr.failure_type
                   FROM failure_records fr
                   WHERE fr.task_ref = t.task_id
                   ORDER BY fr.id DESC
                   LIMIT 1
               ) AS latest_failure_type,
               (
                   SELECT fr.summary
                   FROM failure_records fr
                   WHERE fr.task_ref = t.task_id
                   ORDER BY fr.id DESC
                   LIMIT 1
               ) AS latest_failure_summary,
               (
                   SELECT COUNT(*)
                   FROM attempts a
                   WHERE a.task_id = t.id
               ) AS attempts_count
        FROM tasks t
        {where_sql}
        ORDER BY t.updated_at DESC
        LIMIT ?
        """
        parameters.append(limit)

        with connect_sqlite(self.context.runtime.database_path) as connection:
            rows = connection.execute(sql, tuple(parameters)).fetchall()

        items = [
            {
                "task_id": row["task_id"],
                "cve_id": row["cve_id"],
                "target_kernel": row["target_kernel"],
                "status": row["status"],
                "current_attempt": row["current_attempt"],
                "max_attempts": row["max_attempts"],
                "workspace_dir": row["workspace_dir"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "latest_failure_type": row["latest_failure_type"],
                "latest_failure_summary": row["latest_failure_summary"],
                "attempts_count": row["attempts_count"],
            }
            for row in rows
        ]
        return {"items": items, "total": len(items)}

    def create_task(
        self,
        *,
        cve_id: str,
        target_kernel: str | None = None,
        profile: str | None = None,
        max_attempts: int | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        """创建任务并准备工作区骨架。"""

        runtime = resolve_runtime(
            project_root=self.context.project_root,
            profile_name=profile,
            cli_max_attempts=max_attempts,
        )
        task_repo = self.context.task_repo
        attempt_repo = self.context.attempt_repo
        artifact_repo = self.context.artifact_repo

        final_task_id = task_repo.next_task_id()
        task = TaskContext(
            task_id=final_task_id,
            cve_id=cve_id,
            target_kernel=target_kernel or runtime.default_kernel,
            profile_name=runtime.profile_name,
            status="created",
            max_attempts=runtime.max_attempts,
            current_attempt=0,
            workspace_dir=(runtime.workspace_root / final_task_id).resolve(),
        )

        workspace_guard = WorkspaceGuard(runtime.workspace_root)
        task_dir = workspace_guard.create_task_workspace(task)
        workspace_guard.create_attempt_workspace(task_dir, 1)
        task_repo.create_task(task)

        initial_state = AttemptEngine().create_initial_state(task_id=task.task_id, max_attempts=task.max_attempts)
        attempt_repo.save_attempt_state(initial_state)
        artifact_repo.add_artifact(
            task_id=task.task_id,
            artifact_type="task_context",
            artifact_path=task_dir / "task_context.json",
            metadata={"summary": "任务上下文快照"},
        )

        # Web 表单里的额外字段先单独留痕，后面做多用户和分组时还可以继续扩展。
        request_path = task_dir / "input" / "task_request.json"
        request_payload = {
            "cve_id": cve_id,
            "target_kernel": task.target_kernel,
            "profile": profile,
            "max_attempts": task.max_attempts,
            "note": note,
        }
        request_path.write_text(json.dumps(request_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        artifact_repo.add_artifact(
            task_id=task.task_id,
            artifact_type="task_request",
            artifact_path=request_path,
            metadata={"summary": "Web 创建请求快照"},
        )

        return {
            "task": self._task_payload(task),
            "prepared_attempt_dir": str(task_dir / "attempts" / "001"),
            "request_path": str(request_path),
        }

    def get_task_detail(self, task_id: str) -> dict[str, Any]:
        """返回任务详情页需要的聚合数据。"""

        task = self.context.task_repo.get_task(task_id)
        if task is None:
            raise ValueError(f"未找到任务：{task_id}")

        attempts = self.context.attempt_repo.list_attempts(task_id)
        artifacts = self.context.artifact_repo.list_artifacts(task_id)
        latest_attempt = attempts[-1] if attempts else None
        task_dir = task.workspace_dir.resolve()

        latest_failure_path = None
        latest_validation_path = None
        latest_trace_path = None
        latest_rewrite_plan_path = None
        if latest_attempt is not None:
            attempt_dir = task_dir / "attempts" / f"{latest_attempt.attempt_no:03d}"
            latest_failure_path = attempt_dir / "logs" / "failure_record.json"
            latest_validation_path = attempt_dir / "artifacts" / "validation_report.json"
            latest_trace_path = attempt_dir / "trace" / "harness_trace.json"
            latest_rewrite_plan_path = attempt_dir / "rewrite" / "rewrite_plan.json"

        replay = self.context.build_task_runner().replay_task(task_id) if attempts else {
            "command": "replay",
            "task_id": task_id,
            "latest_attempt_id": None,
            "latest_attempt_status": None,
            "trace_path": None,
            "report_path": None,
            "evaluation_summary_path": None,
            "stage_routes": {},
            "dispatch_modes": {},
            "replay_files": [],
            "comparison": {},
            "status": "empty",
        }

        return {
            "task": self._task_payload(task),
            "patch_bundle": self._load_json(task_dir / "input" / "patch_bundle.json"),
            "analysis": {
                "semantic_card_path": str(task_dir / "analysis" / "semantic_card.json"),
                "constraint_report_path": str(task_dir / "analysis" / "constraint_report.json"),
                "context_bundle_path": str(task_dir / "analysis" / "context" / "context_bundle.json"),
                "analysis_trace_path": str(task_dir / "analysis" / "trace" / "analysis_trace.json"),
            },
            "attempts": [self._attempt_payload(task_dir, item) for item in attempts],
            "latest_failure": self._load_json(latest_failure_path),
            "latest_validation": self._load_json(latest_validation_path),
            "latest_trace": self._load_json(latest_trace_path),
            "latest_rewrite_plan": self._load_json(latest_rewrite_plan_path),
            "evaluation_summary": self._load_json(task_dir / "reports" / "evaluation_summary.json"),
            "reports": {
                "json_path": str(task_dir / "reports" / "report.json"),
                "md_path": str(task_dir / "reports" / "report.md"),
                "evaluation_summary_path": str(task_dir / "reports" / "evaluation_summary.json"),
            },
            "replay": replay,
            "timeline": self._build_timeline(task_dir, attempts),
            "artifact_index": [
                {
                    "artifact_type": artifact.artifact_type,
                    "artifact_path": str(artifact.artifact_path),
                    "relative_path": self._relative_to_workspace(task_dir, artifact.artifact_path),
                    "summary": artifact.summary,
                }
                for artifact in artifacts
            ],
            "workspace_exists": task_dir.exists(),
        }

    def analyze_task(self, task_id: str) -> dict[str, Any]:
        """触发分析阶段。"""

        task = self._require_task(task_id)
        return self.context.build_task_runner(profile_name=task.profile_name, max_attempts=task.max_attempts).analyze_task(task_id)

    def run_task(self, task_id: str) -> dict[str, Any]:
        """执行单轮尝试。"""

        task = self._require_task(task_id)
        return self.context.build_task_runner(profile_name=task.profile_name, max_attempts=task.max_attempts).run_task(task_id)

    def report_task(self, task_id: str) -> dict[str, Any]:
        """生成最终报告。"""

        task = self._require_task(task_id)
        return self.context.build_task_runner(profile_name=task.profile_name, max_attempts=task.max_attempts).build_report(task_id)

    def replay_task(self, task_id: str) -> dict[str, Any]:
        """读取回放信息。"""

        task = self._require_task(task_id)
        return self.context.build_task_runner(profile_name=task.profile_name, max_attempts=task.max_attempts).replay_task(task_id)

    def _task_payload(self, task: TaskContext) -> dict[str, Any]:
        """把任务对象转成接口返回结构。"""

        return {
            "task_id": task.task_id,
            "cve_id": task.cve_id,
            "target_kernel": task.target_kernel,
            "profile_name": task.profile_name,
            "status": task.status,
            "current_attempt": task.current_attempt,
            "max_attempts": task.max_attempts,
            "workspace_dir": str(task.workspace_dir),
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat(),
        }

    def _require_task(self, task_id: str) -> TaskContext:
        """读取任务对象，不存在时直接报错。"""

        task = self.context.task_repo.get_task(task_id)
        if task is None:
            raise ValueError(f"未找到任务：{task_id}")
        return task

    def _attempt_payload(self, task_dir: Path, attempt) -> dict[str, Any]:
        """整理单轮尝试的常用路径和状态。"""

        attempt_dir = task_dir / "attempts" / f"{attempt.attempt_no:03d}"
        return {
            "attempt_id": attempt.attempt_id,
            "attempt_no": attempt.attempt_no,
            "status": attempt.status,
            "failure_type": attempt.failure_type,
            "build_log_path": str(attempt.build_log_path) if attempt.build_log_path else None,
            "module_path": str(attempt.module_path) if attempt.module_path else None,
            "rewritten_patch_path": str(attempt.rewritten_patch_path) if attempt.rewritten_patch_path else None,
            "started_at": attempt.started_at.isoformat(),
            "finished_at": attempt.finished_at.isoformat() if attempt.finished_at else None,
            "failure_record_path": str(attempt_dir / "logs" / "failure_record.json"),
            "validation_report_path": str(attempt_dir / "artifacts" / "validation_report.json"),
            "validation_matrix_path": str(attempt_dir / "artifacts" / "validation_matrix.json"),
            "semantic_guard_path": str(attempt_dir / "artifacts" / "semantic_guard.json"),
            "planning_hints_path": str(attempt_dir / "rewrite" / "planning_hints.json"),
            "harness_trace_path": str(attempt_dir / "trace" / "harness_trace.json"),
            "rewrite_plan_path": str(attempt_dir / "rewrite" / "rewrite_plan.json"),
        }

    def _load_json(self, path: Path | None) -> dict[str, Any] | None:
        """安全读取 JSON 文件。"""

        if path is None or not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def _relative_to_workspace(self, workspace_dir: Path, path: Path) -> str:
        """把产物绝对路径转成相对工作区路径。"""

        resolved = Path(path).resolve()
        try:
            return resolved.relative_to(workspace_dir.resolve()).as_posix()
        except ValueError:
            return str(resolved)

    def _build_timeline(self, task_dir: Path, attempts: list[Any]) -> list[dict[str, Any]]:
        """根据产物落盘情况生成任务详情页的阶段时间线。"""

        latest_attempt = attempts[-1] if attempts else None
        attempt_dir = task_dir / "attempts" / f"{latest_attempt.attempt_no:03d}" if latest_attempt else None
        stages = [
            ("prepare", task_dir / "task_context.json"),
            ("analyze", task_dir / "analysis" / "semantic_card.json"),
            ("diagnose", task_dir / "analysis" / "constraint_report.json"),
            ("plan", attempt_dir / "rewrite" / "rewrite_plan.json" if attempt_dir else None),
            ("rewrite", attempt_dir / "rewrite" / "rewritten.patch" if attempt_dir else None),
            ("build", attempt_dir / "logs" / "build.log" if attempt_dir else None),
            ("classify", attempt_dir / "logs" / "failure_record.json" if attempt_dir else None),
            ("validate", attempt_dir / "artifacts" / "validation_report.json" if attempt_dir else None),
            ("report", task_dir / "reports" / "report.json"),
        ]
        timeline: list[dict[str, Any]] = []
        for stage_name, marker in stages:
            completed = bool(marker and marker.exists())
            timeline.append(
                {
                    "stage": stage_name,
                    "status": "completed" if completed else "pending",
                    "path": str(marker) if marker else None,
                }
            )
        return timeline
