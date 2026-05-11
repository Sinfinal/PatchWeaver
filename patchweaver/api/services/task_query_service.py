"""任务查询与动作执行服务"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from patchweaver.api.deps import ApiContext
from patchweaver.agent.actions import AgentActionName
from patchweaver.agent.health import evaluate_agent_health
from patchweaver.config.resolver import resolve_runtime
from patchweaver.harness.workspace_guard import WorkspaceGuard
from patchweaver.models.task import TaskContext
from patchweaver.observability.run_logger import RunLogger
from patchweaver.runtime_inspector import resolve_task_binding
from patchweaver.task_creation_policy import build_duplicate_scope, build_duplicate_task_notice
from patchweaver.storage.sqlite import connect_sqlite
from patchweaver.utils.path_policy import relativize_payload, to_project_relative


class TaskQueryService:
    """负责任务列表、详情和动作入口"""

    def __init__(self, context: ApiContext) -> None:
        """保存 API 共享上下文"""

        self.context = context
        self.run_logger = RunLogger(context.project_root, context.logging_config)

    def list_tasks(
        self,
        *,
        limit: int = 50,
        cve_id: str | None = None,
        status: str | None = None,
        failure_type: str | None = None,
        target_kernel: str | None = None,
        build_exec_status: str | None = None,
        target_state: str | None = None,
        fixture_group: str | None = None,
        created_at_from: str | None = None,
        created_at_to: str | None = None,
        current_attempt: int | None = None,
    ) -> dict[str, Any]:
        """按筛选条件读取任务列表"""

        fixture_catalog = self._load_fixture_catalog()
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
        if build_exec_status:
            conditions.append("la.build_exec_status = ?")
            parameters.append(build_exec_status)
        if target_state:
            conditions.append("la.target_state = ?")
            parameters.append(target_state)
        if current_attempt is not None:
            conditions.append("t.current_attempt = ?")
            parameters.append(current_attempt)
        normalized_created_from = self._normalize_datetime_filter(created_at_from)
        if normalized_created_from is not None:
            conditions.append("datetime(substr(replace(t.created_at, 'T', ' '), 1, 19)) >= datetime(?)")
            parameters.append(normalized_created_from)
        normalized_created_to = self._normalize_datetime_filter(created_at_to)
        if normalized_created_to is not None:
            conditions.append("datetime(substr(replace(t.created_at, 'T', ' '), 1, 19)) <= datetime(?)")
            parameters.append(normalized_created_to)
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
        if fixture_group:
            normalized_fixture_group = fixture_group.strip().replace("-", "_")
            fixture_clauses: list[str] = []
            for item in fixture_catalog:
                if item["fixture_group"] != normalized_fixture_group:
                    continue
                if item["target_kernel"]:
                    fixture_clauses.append("(t.cve_id = ? AND t.target_kernel = ?)")
                    parameters.extend([item["cve_id"], item["target_kernel"]])
                    continue
                fixture_clauses.append("(t.cve_id = ?)")
                parameters.append(item["cve_id"])
            if not fixture_clauses:
                return {"items": [], "total": 0}
            conditions.append(f"({' OR '.join(fixture_clauses)})")

        where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        sql = f"""
        WITH latest_attempt AS (
            SELECT a.task_id, a.build_exec_status, a.target_state
            FROM attempts a
            JOIN (
                SELECT task_id, MAX(attempt_no) AS max_attempt_no
                FROM attempts
                GROUP BY task_id
            ) latest ON latest.task_id = a.task_id AND latest.max_attempt_no = a.attempt_no
        ),
        attempt_counts AS (
            SELECT task_id, COUNT(*) AS attempts_count
            FROM attempts
            GROUP BY task_id
        ),
        latest_failure AS (
            SELECT fr.task_ref, fr.failure_type, fr.summary
            FROM failure_records fr
            JOIN (
                SELECT task_ref, MAX(id) AS max_id
                FROM failure_records
                GROUP BY task_ref
            ) latest ON latest.task_ref = fr.task_ref AND latest.max_id = fr.id
        )
        SELECT t.task_id, t.cve_id, t.target_kernel, t.target_kernel_source, t.status, t.current_attempt, t.max_attempts,
               t.workspace_dir, t.created_at, t.updated_at,
               lf.failure_type AS latest_failure_type,
               lf.summary AS latest_failure_summary,
               la.build_exec_status AS latest_build_exec_status,
               la.target_state AS latest_target_state,
               COALESCE(ac.attempts_count, 0) AS attempts_count
        FROM tasks t
        LEFT JOIN latest_failure lf ON lf.task_ref = t.task_id
        LEFT JOIN latest_attempt la ON la.task_id = t.id
        LEFT JOIN attempt_counts ac ON ac.task_id = t.id
        {where_sql}
        ORDER BY t.updated_at DESC
        LIMIT ?
        """
        parameters.append(limit)

        with connect_sqlite(self.context.runtime.database_path) as connection:
            rows = connection.execute(sql, tuple(parameters)).fetchall()

        items = []
        for row in rows:
            task_for_health = self.context.task_repo.get_task(row["task_id"])
            attempts_for_health = self.context.attempt_repo.list_attempts(row["task_id"]) if task_for_health is not None else []
            agent_health = (
                evaluate_agent_health(
                    task=task_for_health,
                    attempts=attempts_for_health,
                    project_root=self.context.project_root,
                    write=False,
                )
                if task_for_health is not None
                else None
            )
            fixture_binding = self._resolve_fixture_binding(
                fixture_catalog,
                cve_id=row["cve_id"],
                target_kernel=row["target_kernel"],
            )
            items.append(
                {
                    "task_id": row["task_id"],
                    "cve_id": row["cve_id"],
                    "target_kernel": row["target_kernel"],
                    "target_kernel_source": row["target_kernel_source"],
                    "status": row["status"],
                    "current_attempt": row["current_attempt"],
                    "max_attempts": row["max_attempts"],
                    "workspace_dir": row["workspace_dir"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "latest_failure_type": row["latest_failure_type"],
                    "latest_failure_summary": row["latest_failure_summary"],
                    "latest_build_exec_status": row["latest_build_exec_status"],
                    "latest_target_state": row["latest_target_state"],
                    "attempts_count": row["attempts_count"],
                    "agent_health": agent_health,
                    "fixture_group": fixture_binding["fixture_group"] if fixture_binding else None,
                    "fixture_id": fixture_binding["fixture_id"] if fixture_binding else None,
                }
            )
        return {"items": items, "total": len(items)}

    def create_task(
        self,
        *,
        cve_id: str,
        target_kernel: str | None = None,
        profile: str | None = None,
        max_attempts: int | None = None,
        note: str | None = None,
        force_new: bool = False,
        auto_run: bool = False,
    ) -> dict[str, Any]:
        """创建任务并准备工作区骨架"""

        runtime = resolve_runtime(
            project_root=self.context.project_root,
            profile_name=profile,
            cli_max_attempts=max_attempts,
        )
        task_repo = self.context.task_repo
        artifact_repo = self.context.artifact_repo

        final_task_id = task_repo.next_task_id()
        target_kernel_value, target_kernel_source, machine_profile = resolve_task_binding(
            build_config=self.context.build_config,
            configured_default_kernel=runtime.default_kernel,
            cli_target_kernel=target_kernel,
        )
        duplicate_scope = build_duplicate_scope(
            cve_id=cve_id,
            target_kernel=target_kernel_value,
            target_kernel_source=target_kernel_source,
            profile_name=runtime.profile_name,
            machine_profile=machine_profile,
        )
        if not force_new:
            existing_task = task_repo.find_latest_equivalent_task(
                cve_id=cve_id,
                target_kernel=target_kernel_value,
                profile_name=runtime.profile_name,
                target_kernel_source=target_kernel_source,
                machine_profile=machine_profile,
            )
            if existing_task is not None:
                latest_attempt = self.context.attempt_repo.get_latest_attempt(existing_task.task_id)
                existing_failure = None
                if latest_attempt is None:
                    existing_failure = self._load_json(existing_task.workspace_dir.resolve() / "analysis" / "trace" / "failure_record.json")
                existing_task_payload = self._task_payload(
                    existing_task,
                    latest_attempt=latest_attempt,
                    latest_failure=existing_failure,
                )
                duplicate_notice = build_duplicate_task_notice(existing_task, latest_attempt)
                self.run_logger.info(
                    "web.create_task_duplicate",
                    duplicate_notice["message"],
                    cve_id=cve_id,
                    existing_task_id=existing_task.task_id,
                    reason=duplicate_notice["reason"],
                    duplicate_scope=duplicate_scope,
                )
                return {
                    "status": "duplicate",
                    "created": False,
                    "message": duplicate_notice["message"],
                    "decision": duplicate_notice["decision"],
                    "reason": duplicate_notice["reason"],
                    "recommended_action": duplicate_notice["recommended_action"],
                    "next_steps": duplicate_notice["next_steps"],
                    "duplicate_scope": duplicate_scope,
                    "task": existing_task_payload,
                    "existing_task": existing_task_payload,
                }

        task = TaskContext(
            task_id=final_task_id,
            cve_id=cve_id,
            target_kernel=target_kernel_value,
            target_kernel_source=target_kernel_source,
            profile_name=runtime.profile_name,
            status="created",
            max_attempts=runtime.max_attempts,
            current_attempt=0,
            workspace_dir=(runtime.workspace_root / final_task_id).resolve(),
            machine_profile=machine_profile,
        )

        workspace_guard = WorkspaceGuard(runtime.workspace_root, self.context.project_root)
        task_dir = workspace_guard.create_task_workspace(task)
        task_repo.create_task(task)
        artifact_repo.add_artifact(
            task_id=task.task_id,
            artifact_type="task_context",
            artifact_path=task_dir / "task_context.json",
            metadata={"summary": "任务上下文快照"},
        )

        # Web 表单里的额外字段先单独留痕，后面做多用户和分组时还可以继续扩展
        workspace_guard.ensure_task_input_workspace(task_dir)
        request_path = task_dir / "input" / "task_request.json"
        request_payload = {
            "cve_id": cve_id,
            "target_kernel": task.target_kernel,
            "target_kernel_source": task.target_kernel_source,
            "profile": profile,
            "max_attempts": task.max_attempts,
            "note": note,
            "auto_run": auto_run,
            "machine_profile": machine_profile.model_dump(mode="json"),
        }
        request_path.write_text(json.dumps(request_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        artifact_repo.add_artifact(
            task_id=task.task_id,
            artifact_type="task_request",
            artifact_path=request_path,
            metadata={"summary": "Web 创建请求快照"},
        )
        self.run_logger.info(
            "web.create_task",
            "通过 Web 创建任务。",
            task_id=task.task_id,
            cve_id=task.cve_id,
            profile_name=task.profile_name,
            target_kernel=task.target_kernel,
            target_kernel_source=task.target_kernel_source,
        )

        return {
            "status": "ok",
            "created": True,
            "auto_run": auto_run,
            "auto_run_status": "scheduled" if auto_run else "disabled",
            "task": self._task_payload(task),
            "next_attempt_dir": self._path(task_dir / "attempts" / "001"),
            "prepared_attempt_dir": self._path(task_dir / "attempts" / "001"),
            "request_path": self._path(request_path),
        }

    def auto_run_task(self, task_id: str) -> dict[str, Any]:
        """按受控 Agent action 顺序推进任务主链。"""

        task = self._require_task(task_id)
        runner = self.context.build_task_runner(profile_name=task.profile_name, max_attempts=task.max_attempts)
        registry = runner.build_action_registry()
        task_dir = task.workspace_dir.resolve()
        trace_path = task_dir / "agent" / "auto_workflow_trace.json"
        trace_path.parent.mkdir(parents=True, exist_ok=True)

        results: list[dict[str, Any]] = []
        for action in [
            AgentActionName.ANALYZE_TASK,
            AgentActionName.RUN_TASK,
            AgentActionName.REPORT_TASK,
            AgentActionName.REPLAY_TASK,
        ]:
            result = registry.execute(action, task_id)
            result_payload = result.model_dump(mode="json")
            results.append(result_payload)
            if result.status == "failed":
                break
            if action == AgentActionName.ANALYZE_TASK and result.payload.get("status") == "failed":
                break
            if action == AgentActionName.RUN_TASK and result.payload.get("status") in {"created", "running"}:
                break

        payload = {
            "task_id": task_id,
            "status": "ok" if results and results[-1].get("status") != "failed" else "failed",
            "actions": results,
        }
        trace_path.write_text(json.dumps(relativize_payload(payload, self.context.project_root), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.context.artifact_repo.add_artifact(
            task_id=task_id,
            artifact_type="agent_auto_workflow_trace",
            artifact_path=trace_path,
            metadata={"summary": "Web 自动运行入口动作轨迹"},
        )
        self.run_logger.info("web.auto_run_task", "Web 自动运行入口已推进主链", task_id=task_id, status=payload["status"])
        return payload

    def get_task_detail(self, task_id: str) -> dict[str, Any]:
        """返回任务详情页需要的聚合数据"""

        task = self.context.task_repo.get_task(task_id)
        if task is None:
            raise ValueError(f"未找到任务：{task_id}")

        # 详情页是一个聚合视图
        # 这里一次把 attempts、artifacts、最新失败和最新验证都拼出来
        attempts = self.context.attempt_repo.list_attempts(task_id)
        artifacts = self.context.artifact_repo.list_artifacts(task_id)
        latest_attempt = attempts[-1] if attempts else None
        task_dir = task.workspace_dir.resolve()

        latest_failure_path = None
        latest_validation_path = None
        latest_trace_path = None
        latest_rewrite_plan_path = None
        latest_apply_precheck_path = None
        latest_build_summary_path = None
        if latest_attempt is not None:
            attempt_dir = task_dir / "attempts" / f"{latest_attempt.attempt_no:03d}"
            latest_failure_path = attempt_dir / "logs" / "failure_record.json"
            latest_validation_path = attempt_dir / "artifacts" / "validation_report.json"
            latest_trace_path = attempt_dir / "trace" / "harness_trace.json"
            latest_rewrite_plan_path = attempt_dir / "rewrite" / "rewrite_plan.json"
            latest_apply_precheck_path = attempt_dir / "rewrite" / "apply_precheck.json"
            latest_build_summary_path = attempt_dir / "artifacts" / "build_summary.json"
        else:
            analysis_failure_path = task_dir / "analysis" / "trace" / "failure_record.json"
            if analysis_failure_path.exists():
                latest_failure_path = analysis_failure_path

        # replay 会顺着 attempts、trace 和报告再做一次归并
        # 没有尝试记录时直接给空结果，避免详情页首开就走一串无效读取
        replay = relativize_payload(self.context.build_task_runner().replay_task(task_id), self.context.project_root) if attempts else {
            "command": "replay",
            "task_id": task_id,
            "latest_attempt_id": None,
            "latest_attempt_status": None,
            "latest_failure_type": None,
            "latest_build_exec_status": None,
            "latest_target_state": None,
            "trace_path": None,
            "report_path": None,
            "evaluation_summary_path": None,
            "stage_routes": {},
            "dispatch_modes": {},
            "replay_files": [],
            "comparison": {},
            "status": "empty",
        }

        latest_failure = self._load_json(latest_failure_path)
        latest_validation = self._load_json(latest_validation_path)
        latest_trace = self._load_json(latest_trace_path)
        latest_rewrite_plan = self._load_json(latest_rewrite_plan_path)
        latest_apply_precheck = self._load_json(latest_apply_precheck_path)
        latest_build_summary = self._load_json(latest_build_summary_path)
        agent_decision_summary = self._build_agent_decision_summary(
            task=task,
            task_dir=task_dir,
            latest_attempt=latest_attempt,
            latest_failure=latest_failure,
            latest_rewrite_plan=latest_rewrite_plan,
            latest_apply_precheck=latest_apply_precheck,
            latest_build_summary=latest_build_summary,
        )
        agent_health = evaluate_agent_health(
            task=task,
            attempts=attempts,
            project_root=self.context.project_root,
        )

        return {
            # task 是顶部摘要
            # analysis、attempts、reports、replay 对应页面里的四块主视图
            "task": self._task_payload(task, latest_attempt=latest_attempt, latest_failure=latest_failure, agent_health=agent_health),
            "patch_bundle": self._load_json(task_dir / "input" / "patch_bundle.json"),
            "analysis": {
                "semantic_card_path": self._path(task_dir / "analysis" / "semantic_card.json"),
                "semantic_card_enrichment_path": self._path(task_dir / "analysis" / "trace" / "semantic_card_enrichment.json"),
                "constraint_report_path": self._path(task_dir / "analysis" / "constraint_report.json"),
                "context_bundle_path": self._path(task_dir / "analysis" / "context" / "context_bundle.json"),
                "analysis_trace_path": self._path(task_dir / "analysis" / "trace" / "analysis_trace.json"),
            },
            "attempts": [self._attempt_payload(task_dir, item) for item in attempts],
            "latest_failure": latest_failure,
            "latest_validation": latest_validation,
            "latest_trace": latest_trace,
            "latest_rewrite_plan": latest_rewrite_plan,
            "agent_decision_summary": agent_decision_summary,
            "agent_health": agent_health,
            "evaluation_summary": self._load_json(task_dir / "reports" / "evaluation_summary.json"),
            "reports": {
                "json_path": self._path(task_dir / "reports" / "report.json"),
                "md_path": self._path(task_dir / "reports" / "report.md"),
                "evaluation_summary_path": self._path(task_dir / "reports" / "evaluation_summary.json"),
            },
            "report_closure": {
                "report_json_path": self._path(task_dir / "reports" / "report.json"),
                "report_md_path": self._path(task_dir / "reports" / "report.md"),
                "build_log_path": self._path(latest_attempt.build_log_path) if latest_attempt and latest_attempt.build_log_path else None,
                "validation_report_path": self._path(latest_validation_path) if latest_validation_path is not None else None,
                "trace_path": self._path(latest_trace_path) if latest_trace_path is not None else None,
                "workspace_dir": self._path(task_dir),
                "closure_ok": bool(
                    (task_dir / "reports" / "report.json").exists()
                    and (task_dir / "reports" / "report.md").exists()
                    and latest_validation_path is not None
                    and latest_validation_path.exists()
                    and latest_trace_path is not None
                    and latest_trace_path.exists()
                    and latest_attempt is not None
                    and latest_attempt.build_log_path is not None
                    and Path(latest_attempt.build_log_path).exists()
                ),
            },
            "replay": replay,
            "process_summary": self._build_process_summary(
                task=task,
                task_dir=task_dir,
                latest_attempt=latest_attempt,
                latest_failure=latest_failure,
                latest_validation=latest_validation,
                latest_apply_precheck=latest_apply_precheck,
                latest_build_summary=latest_build_summary,
                replay=replay,
            ),
            "stage_view": self._build_stage_view(
                task=task,
                task_dir=task_dir,
                latest_attempt=latest_attempt,
                latest_failure=latest_failure,
                latest_validation=latest_validation,
                latest_apply_precheck=latest_apply_precheck,
                latest_build_summary=latest_build_summary,
            ),
            # timeline 和 artifact_index 都是给前端直接展示用的
            # 后端先把阶段完成情况和产物索引算好，页面层就不用再猜
            "timeline": self._build_timeline(task_dir, attempts),
            "artifact_index": [
                {
                    "artifact_type": artifact.artifact_type,
                    "artifact_path": self._path(artifact.artifact_path),
                    "relative_path": self._relative_to_workspace(task_dir, artifact.artifact_path),
                    "summary": artifact.summary,
                }
                for artifact in artifacts
            ],
            "workspace_exists": task_dir.exists(),
        }

    def get_agent_decision_summary(self, task_id: str) -> dict[str, Any]:
        """返回任务级 Agent 决策摘要，供 Web/API 和百炼入口直接展示"""

        task = self._require_task(task_id)
        attempts = self.context.attempt_repo.list_attempts(task_id)
        latest_attempt = attempts[-1] if attempts else None
        task_dir = task.workspace_dir.resolve()
        attempt_dir = task_dir / "attempts" / f"{latest_attempt.attempt_no:03d}" if latest_attempt else None

        return self._build_agent_decision_summary(
            task=task,
            task_dir=task_dir,
            latest_attempt=latest_attempt,
            latest_failure=self._load_json(attempt_dir / "logs" / "failure_record.json") if attempt_dir else None,
            latest_rewrite_plan=self._load_json(attempt_dir / "rewrite" / "rewrite_plan.json") if attempt_dir else None,
            latest_apply_precheck=self._load_json(attempt_dir / "rewrite" / "apply_precheck.json") if attempt_dir else None,
            latest_build_summary=self._load_json(attempt_dir / "artifacts" / "build_summary.json") if attempt_dir else None,
        )

    def analyze_task(self, task_id: str) -> dict[str, Any]:
        """触发分析阶段"""

        task = self._require_task(task_id)
        payload = self.context.build_task_runner(profile_name=task.profile_name, max_attempts=task.max_attempts).analyze_task(task_id)
        self.run_logger.info("web.analyze_task", "通过 Web 触发分析阶段。", task_id=task_id)
        return payload

    def run_task(self, task_id: str) -> dict[str, Any]:
        """执行单轮尝试"""

        task = self._require_task(task_id)
        payload = self.context.build_task_runner(profile_name=task.profile_name, max_attempts=task.max_attempts).run_task(task_id)
        self.run_logger.info("web.run_task", "通过 Web 触发单轮执行。", task_id=task_id)
        return payload

    def report_task(self, task_id: str) -> dict[str, Any]:
        """生成最终报告"""

        task = self._require_task(task_id)
        payload = self.context.build_task_runner(profile_name=task.profile_name, max_attempts=task.max_attempts).build_report(task_id)
        self.run_logger.info("web.report_task", "通过 Web 生成最终报告。", task_id=task_id)
        return payload

    def replay_task(self, task_id: str) -> dict[str, Any]:
        """读取回放信息"""

        task = self._require_task(task_id)
        payload = self.context.build_task_runner(profile_name=task.profile_name, max_attempts=task.max_attempts).replay_task(task_id)
        self.run_logger.info("web.replay_task", "通过 Web 读取任务回放。", task_id=task_id)
        return payload

    def _build_agent_decision_summary(
        self,
        *,
        task: TaskContext,
        task_dir: Path,
        latest_attempt: Any | None,
        latest_failure: dict[str, Any] | None,
        latest_rewrite_plan: dict[str, Any] | None,
        latest_apply_precheck: dict[str, Any] | None,
        latest_build_summary: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """从工作区产物归并 Agent 修复意图、路线选择和失败归因"""

        repair_intent_path = task_dir / "analysis" / "repair_intent.json"
        report_path = task_dir / "reports" / "report.json"
        agent_workflow_trace_path = task_dir / "agent" / "agent_workflow_trace.json"
        repair_intent = self._load_json(repair_intent_path)
        report_json = self._load_json(report_path)
        agent_workflow_trace = self._load_json(agent_workflow_trace_path)
        latest_failure_type = self._latest_failure_type(latest_attempt, latest_failure, latest_build_summary, latest_apply_precheck)
        latest_build_exec_status = self._latest_build_exec_status(latest_attempt, latest_build_summary, latest_apply_precheck)
        selected_recipe = self._first_present(
            latest_rewrite_plan,
            report_json,
            keys=("selected_recipe", "recipe", "recipe_name"),
        )
        intent_strategy = self._first_present(
            repair_intent,
            report_json,
            keys=("recommended_strategy", "repair_strategy", "strategy"),
        )
        selected_strategy = self._first_present(
            latest_rewrite_plan,
            latest_build_summary,
            latest_apply_precheck,
            report_json,
            keys=("selected_strategy", "strategy", "route", "rewrite_strategy"),
        )
        final_strategy = selected_strategy or selected_recipe or intent_strategy
        agent_next_action = self._first_present(
            latest_failure,
            latest_build_summary,
            latest_apply_precheck,
            report_json,
            keys=("agent_next_action", "next_action", "recommended_action"),
        ) or self._next_action_for_failure(latest_failure_type, latest_build_exec_status)
        diagnostic_details = self._first_present(
            latest_failure,
            latest_build_summary,
            latest_apply_precheck,
            report_json,
            keys=("diagnostic_details", "diagnostics", "details", "root_cause_details"),
        )
        if diagnostic_details is None and latest_failure is not None:
            diagnostic_details = {
                "summary": latest_failure.get("summary"),
                "evidence": latest_failure.get("evidence") or [],
            }

        attempt_dir = task_dir / "attempts" / f"{latest_attempt.attempt_no:03d}" if latest_attempt else None
        failure_record_path = (
            attempt_dir / "logs" / "failure_record.json"
            if attempt_dir
            else task_dir / "analysis" / "trace" / "failure_record.json"
        )
        repair_intent_summary = None
        if repair_intent is not None:
            repair_intent_summary = {
                "cve_id": repair_intent.get("cve_id") or task.cve_id,
                "bug_class": repair_intent.get("bug_class"),
                "root_cause": repair_intent.get("root_cause"),
                "vulnerability_conditions": repair_intent.get("vulnerability_conditions") or [],
                "guard_conditions": repair_intent.get("guard_conditions") or [],
                "guard_sites": repair_intent.get("guard_sites") or [],
                "safe_exits": repair_intent.get("safe_exits") or [],
                "preserved_side_effects": repair_intent.get("preserved_side_effects") or [],
                "touched_files": repair_intent.get("touched_files") or [],
                "touched_functions": repair_intent.get("touched_functions") or [],
                "touched_state": repair_intent.get("touched_state") or [],
                "recommended_strategy": repair_intent.get("recommended_strategy"),
                "confidence": repair_intent.get("confidence"),
                "evidence": repair_intent.get("evidence") or [],
            }

        strategy_switched = bool(
            intent_strategy
            and final_strategy
            and str(intent_strategy) not in {str(final_strategy), str(selected_recipe)}
        )
        return {
            "task_id": task.task_id,
            "attempt_id": latest_attempt.attempt_id if latest_attempt is not None else None,
            "attempt_no": latest_attempt.attempt_no if latest_attempt is not None else None,
            "repair_intent": repair_intent_summary,
            "selected_recipe": selected_recipe,
            "selected_strategy": selected_strategy,
            "strategy": final_strategy,
            "strategy_switch": {
                "repair_intent_strategy": intent_strategy,
                "selected_recipe": selected_recipe,
                "selected_strategy": selected_strategy,
                "final_strategy": final_strategy,
                "switched": strategy_switched,
                "reason": self._first_present(latest_rewrite_plan, report_json, keys=("selection_reason", "strategy_reason", "reason")),
            },
            "agent_next_action": agent_next_action,
            "workflow_trace": self._agent_workflow_trace_summary(
                agent_workflow_trace,
                trace_path=agent_workflow_trace_path,
            ),
            "failure_type": latest_failure_type,
            "failure_record": {
                "summary": (latest_failure or {}).get("summary"),
                "stage_name": (latest_failure or {}).get("stage_name"),
                "failure_type": (latest_failure or {}).get("failure_type"),
                "evidence": (latest_failure or {}).get("evidence") or [],
                "diagnostic_details": diagnostic_details,
                "raw": latest_failure,
            },
            "diagnostic_details": diagnostic_details,
            "state_conflicts": self._state_conflicts(
                latest_attempt=latest_attempt,
                latest_failure=latest_failure,
                latest_apply_precheck=latest_apply_precheck,
                latest_build_summary=latest_build_summary,
            ),
            "source_paths": {
                "repair_intent": self._path(repair_intent_path),
                "rewrite_plan": self._path(attempt_dir / "rewrite" / "rewrite_plan.json") if attempt_dir else None,
                "failure_record": self._path(failure_record_path),
                "build_summary": self._path(attempt_dir / "artifacts" / "build_summary.json") if attempt_dir else None,
                "report_json": self._path(report_path),
                "agent_workflow_trace": self._path(agent_workflow_trace_path),
            },
            "source_exists": {
                "repair_intent": repair_intent_path.exists(),
                "rewrite_plan": bool(attempt_dir and (attempt_dir / "rewrite" / "rewrite_plan.json").exists()),
                "failure_record": failure_record_path.exists(),
                "build_summary": bool(attempt_dir and (attempt_dir / "artifacts" / "build_summary.json").exists()),
                "report_json": report_path.exists(),
                "agent_workflow_trace": agent_workflow_trace_path.exists(),
            },
        }

    def _agent_workflow_trace_summary(
        self,
        payload: dict[str, Any] | None,
        *,
        trace_path: Path,
    ) -> dict[str, Any]:
        """整理 Agent workflow trace 给 Web/API 展示。"""

        if not isinstance(payload, dict):
            return {
                "present": False,
                "trace_path": self._path(trace_path),
                "latest_decision": None,
                "terminal_stop_reason": None,
            }
        decisions = payload.get("decisions")
        latest = decisions[-1] if isinstance(decisions, list) and decisions else None
        latest_decision = latest if isinstance(latest, dict) else None
        return {
            "present": True,
            "trace_path": self._path(trace_path),
            "decision_count": len(decisions) if isinstance(decisions, list) else 0,
            "latest_decision": latest_decision,
            "terminal_stop_reason": latest_decision.get("reason")
            if latest_decision is not None and bool(latest_decision.get("terminal"))
            else None,
        }

    def _first_present(self, *sources: dict[str, Any] | None, keys: tuple[str, ...]) -> Any | None:
        """按优先级从多个 JSON 产物读取第一个非空字段"""

        for source in sources:
            if not isinstance(source, dict):
                continue
            for key in keys:
                value = source.get(key)
                if value not in (None, "", [], {}):
                    return value
        return None

    def _task_payload(
        self,
        task: TaskContext,
        latest_attempt=None,
        latest_failure: dict[str, Any] | None = None,
        agent_health: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """把任务对象转成接口返回结构"""

        fixture_binding = self._resolve_fixture_binding(
            self._load_fixture_catalog(),
            cve_id=task.cve_id,
            target_kernel=task.target_kernel,
        )
        return {
            "task_id": task.task_id,
            "cve_id": task.cve_id,
            "target_kernel": task.target_kernel,
            "target_kernel_source": task.target_kernel_source,
            "profile_name": task.profile_name,
            "status": task.status,
            "current_attempt": task.current_attempt,
            "max_attempts": task.max_attempts,
            "workspace_dir": self._path(task.workspace_dir),
            "machine_profile": task.machine_profile.model_dump(mode="json") if task.machine_profile is not None else None,
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat(),
            "latest_failure_type": latest_attempt.failure_type if latest_attempt is not None else (latest_failure or {}).get("failure_type"),
            "latest_build_exec_status": latest_attempt.build_exec_status if latest_attempt is not None else None,
            "latest_target_state": latest_attempt.target_state if latest_attempt is not None else None,
            "agent_health": agent_health,
            "fixture_group": fixture_binding["fixture_group"] if fixture_binding else None,
            "fixture_id": fixture_binding["fixture_id"] if fixture_binding else None,
        }

    def _require_task(self, task_id: str) -> TaskContext:
        """读取任务对象，不存在时直接报错"""

        task = self.context.task_repo.get_task(task_id)
        if task is None:
            raise ValueError(f"未找到任务：{task_id}")
        return task

    def _attempt_payload(self, task_dir: Path, attempt) -> dict[str, Any]:
        """整理单轮尝试的常用路径和状态"""

        attempt_dir = task_dir / "attempts" / f"{attempt.attempt_no:03d}"
        return {
            "attempt_id": attempt.attempt_id,
            "attempt_no": attempt.attempt_no,
            "status": attempt.status,
            "failure_type": attempt.failure_type,
            "build_exec_status": attempt.build_exec_status,
            "target_state": attempt.target_state,
            "build_log_path": self._path(attempt.build_log_path) if attempt.build_log_path else None,
            "module_path": self._path(attempt.module_path) if attempt.module_path else None,
            "rewritten_patch_path": self._path(attempt.rewritten_patch_path) if attempt.rewritten_patch_path else None,
            "started_at": attempt.started_at.isoformat(),
            "finished_at": attempt.finished_at.isoformat() if attempt.finished_at else None,
            "failure_record_path": self._path(attempt_dir / "logs" / "failure_record.json"),
            "validation_report_path": self._path(attempt_dir / "artifacts" / "validation_report.json"),
            "validation_matrix_path": self._path(attempt_dir / "artifacts" / "validation_matrix.json"),
            "semantic_guard_path": self._path(attempt_dir / "artifacts" / "semantic_guard.json"),
            "planning_hints_path": self._path(attempt_dir / "rewrite" / "planning_hints.json"),
            "harness_trace_path": self._path(attempt_dir / "trace" / "harness_trace.json"),
            "rewrite_plan_path": self._path(attempt_dir / "rewrite" / "rewrite_plan.json"),
        }

    def _load_json(self, path: Path | None) -> dict[str, Any] | None:
        """安全读取 JSON 文件"""

        if path is None or not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def _build_process_summary(
        self,
        *,
        task: TaskContext,
        task_dir: Path,
        latest_attempt: Any | None,
        latest_failure: dict[str, Any] | None,
        latest_validation: dict[str, Any] | None,
        latest_apply_precheck: dict[str, Any] | None,
        latest_build_summary: dict[str, Any] | None,
        replay: dict[str, Any],
    ) -> dict[str, Any]:
        """按文档口径给详情页输出一份主流程摘要"""

        latest_failure_type = self._latest_failure_type(latest_attempt, latest_failure, latest_build_summary, latest_apply_precheck)
        latest_target_state = self._latest_target_state(latest_attempt, latest_build_summary, latest_apply_precheck)
        latest_build_exec_status = self._latest_build_exec_status(latest_attempt, latest_build_summary, latest_apply_precheck)
        validation_status = str((latest_validation or {}).get("status") or "")
        state_conflicts = self._state_conflicts(
            latest_attempt=latest_attempt,
            latest_failure=latest_failure,
            latest_apply_precheck=latest_apply_precheck,
            latest_build_summary=latest_build_summary,
        )

        if latest_target_state == "target_already_patched" or latest_failure_type == "target_already_patched":
            overall_status = "skipped"
            current_stage = "build"
            headline = "目标已修复 / 构建未执行"
            reached_effect = "已完成补丁来源、语义分析、改写规划和目标源码状态判定。"
            missing_effect = "未进入真实 kpatch-build，未产出 .ko，未执行 load/unload/smoke。"
            problem = "目标源码树已经包含该修复，不属于普通构建失败。"
            analysis = "按控制面和报告文档口径，该状态应作为 target_already_patched 展示。"
            next_action = "切换未修复源码树或保留该任务作为已修复态样例。"
            primary_evidence_path = self._path(task_dir / "attempts" / f"{latest_attempt.attempt_no:03d}" / "logs" / "failure_record.json") if latest_attempt else None
        elif latest_attempt is None and latest_failure_type:
            overall_status = "failed"
            current_stage = str((latest_failure or {}).get("stage_name") or "analysis")
            headline = "任务在构建前已明确失败"
            reached_effect = "已完成前置检查并形成结构化失败归因。"
            missing_effect = "未进入改写、构建和动态验证。"
            problem = latest_failure_type
            analysis = str((latest_failure or {}).get("summary") or "构建前失败，未产生 attempt。")
            next_action = self._next_action_for_failure(latest_failure_type, latest_build_exec_status)
            primary_evidence_path = self._path(task_dir / "analysis" / "trace" / "failure_record.json")
        elif latest_attempt is None:
            overall_status = "pending"
            current_stage = "prepare"
            headline = "任务已创建，尚未进入尝试轮"
            reached_effect = "任务上下文已建立。"
            missing_effect = "尚未完成分析、改写、构建和验证。"
            problem = None
            analysis = "当前还没有 attempt 记录，不能推断构建或验证结论。"
            next_action = "先执行分析，再执行一轮尝试。"
            primary_evidence_path = self._path(task_dir / "task_context.json")
        elif latest_attempt.status == "built" and validation_status == "passed":
            overall_status = "success"
            current_stage = "validate"
            headline = "热补丁已构建并通过验证"
            reached_effect = "已产出构建结果，并完成验证报告。"
            missing_effect = "无关键缺口。"
            problem = None
            analysis = "最近一轮构建和验证证据均已就绪。"
            next_action = "可进入报告、回放和交付展示。"
            primary_evidence_path = self._path(task_dir / "attempts" / f"{latest_attempt.attempt_no:03d}" / "artifacts" / "validation_report.json")
        elif latest_attempt.status == "built":
            overall_status = "pending"
            current_stage = "validate"
            headline = "构建已完成，验证证据待补齐"
            reached_effect = "已进入成功侧并形成构建产物记录。"
            missing_effect = "验证报告、验证矩阵或动态验证日志仍需补齐。"
            problem = None
            analysis = "按报告文档口径，该状态属于 success pending，不能直接宣称闭环成功。"
            next_action = "补齐 validation_report、validation_matrix 和动态验证日志。"
            primary_evidence_path = self._path(latest_attempt.build_log_path) if latest_attempt.build_log_path else None
        elif latest_attempt.status == "failed":
            overall_status = "failed"
            current_stage = "build" if latest_build_exec_status == "executed" else "build_precheck"
            headline = "构建链路失败"
            reached_effect = "已完成来源、分析、约束诊断、规划和改写，并形成失败证据。"
            missing_effect = "未产出可加载 .ko，动态验证未进入成功闭环。"
            problem = latest_failure_type or "unknown"
            analysis = str((latest_failure or {}).get("summary") or (latest_build_summary or {}).get("summary") or "请查看 failure_record 和 build.log。")
            next_action = self._next_action_for_failure(latest_failure_type, latest_build_exec_status)
            primary_evidence_path = self._path(task_dir / "attempts" / f"{latest_attempt.attempt_no:03d}" / "logs" / "failure_record.json")
        elif task.status in {"created", "analyzed", "running"}:
            overall_status = "running" if task.status == "running" else "pending"
            current_stage = "analysis" if task.status == "analyzed" else "prepare"
            headline = "任务尚未形成最终构建或验证结论"
            reached_effect = "已完成部分前置阶段。"
            missing_effect = "尚未形成最终构建、失败归因或验证结论。"
            problem = None
            analysis = "不能把未完成状态误报成成功或失败。"
            next_action = "继续执行下一阶段。"
            primary_evidence_path = self._path(task_dir / "task_context.json")
        else:
            overall_status = "pending"
            current_stage = task.status
            headline = "任务处于中间状态"
            reached_effect = "已有部分阶段产物。"
            missing_effect = "最终构建和验证结论仍需结合证据确认。"
            problem = latest_failure_type
            analysis = "当前状态无法仅凭任务状态字段判断，需要查看阶段证据。"
            next_action = "优先查看最新 attempt、failure_record、build.log 和 replay。"
            primary_evidence_path = self._path(task_dir)

        return {
            "overall_status": overall_status,
            "current_stage": current_stage,
            "headline": headline,
            "reached_effect": reached_effect,
            "missing_effect": missing_effect,
            "problem": problem,
            "analysis": analysis,
            "next_action": next_action,
            "primary_evidence_path": primary_evidence_path,
            "current_attempt_no": latest_attempt.attempt_no if latest_attempt is not None else None,
            "latest_failure_type": latest_failure_type,
            "latest_build_exec_status": latest_build_exec_status,
            "latest_target_state": latest_target_state,
            "replay_status": replay.get("status"),
            "state_conflicts": state_conflicts,
        }

    def _build_stage_view(
        self,
        *,
        task: TaskContext,
        task_dir: Path,
        latest_attempt: Any | None,
        latest_failure: dict[str, Any] | None,
        latest_validation: dict[str, Any] | None,
        latest_apply_precheck: dict[str, Any] | None,
        latest_build_summary: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """输出前端可直接展示的阶段视图，避免页面端重推业务结论"""

        attempt_dir = task_dir / "attempts" / f"{latest_attempt.attempt_no:03d}" if latest_attempt else None
        latest_failure_type = self._latest_failure_type(latest_attempt, latest_failure, latest_build_summary, latest_apply_precheck)
        latest_target_state = self._latest_target_state(latest_attempt, latest_build_summary, latest_apply_precheck)
        latest_build_exec_status = self._latest_build_exec_status(latest_attempt, latest_build_summary, latest_apply_precheck)
        target_already_patched = latest_target_state == "target_already_patched" or latest_failure_type == "target_already_patched"

        validation_status = str((latest_validation or {}).get("status") or "")
        source_failure_path = task_dir / "analysis" / "trace" / "failure_record.json"
        source_fetch_trace = self._load_json(task_dir / "analysis" / "trace" / "source_fetch_trace.json")
        source_failed = latest_failure_type == "source_unavailable" or (source_fetch_trace or {}).get("status") == "failed"
        report_json_path = task_dir / "reports" / "report.json"
        report_has_real_input = latest_attempt is not None or latest_failure is not None or (task_dir / "analysis" / "semantic_card.json").exists()
        report_complete = report_json_path.exists() and report_has_real_input

        stage_nodes = [
            self._stage_node(
                stage="prepare",
                label="准备",
                status="success" if (task_dir / "task_context.json").exists() else "pending",
                current_effect="任务上下文和工作区已建立。" if (task_dir / "task_context.json").exists() else "等待任务上下文落盘。",
                missing_effect="无" if (task_dir / "task_context.json").exists() else "缺少 task_context.json。",
                problem=None,
                analysis="该阶段只确认任务输入与工作区，不判定补丁是否可修复。",
                next_action="进入来源获取与语义分析。",
                evidence_paths=[task_dir / "task_context.json"],
            ),
            self._stage_node(
                stage="source",
                label="来源获取",
                status="failed" if source_failed else ("success" if (task_dir / "input" / "patch_bundle.json").exists() else "pending"),
                current_effect="来源解析失败，未找到可下载 patch。" if source_failed else ("已获取 CVE 修复来源、patch bundle 和来源证据。" if (task_dir / "input" / "patch_bundle.json").exists() else "尚未获取 patch bundle。"),
                missing_effect="缺少可用于改写的 stable/upstream patch。" if source_failed else ("无" if (task_dir / "input" / "patch_bundle.json").exists() else "缺少 patch_bundle/source_evidence/raw_patch。"),
                problem="source_unavailable" if source_failed else None,
                analysis=str((latest_failure or {}).get("summary") or "赛题要求从 CVE 定位上游或 stable 修复补丁，本阶段承接该要求。"),
                next_action=self._next_action_for_failure("source_unavailable", None) if source_failed else "进入语义理解和约束诊断。",
                evidence_paths=[
                    task_dir / "input" / "patch_bundle.json",
                    task_dir / "input" / "source_evidence.json",
                    task_dir / "analysis" / "trace" / "source_fetch_trace.json",
                    source_failure_path,
                ],
            ),
            self._stage_node(
                stage="analysis",
                label="语义分析",
                status="skipped" if source_failed else ("success" if (task_dir / "analysis" / "semantic_card.json").exists() else "pending"),
                current_effect="来源不可用，语义分析未执行。" if source_failed else ("已生成修复意图和触达对象摘要。" if (task_dir / "analysis" / "semantic_card.json").exists() else "尚未形成语义卡片。"),
                missing_effect="未获得 patch，无法生成 semantic_card。" if source_failed else ("无" if (task_dir / "analysis" / "semantic_card.json").exists() else "缺少 semantic_card.json。"),
                problem="source_unavailable" if source_failed else None,
                analysis="该阶段用于守住语义一致性，避免后续改写偏离上游修复意图。",
                next_action="先解决来源获取问题。" if source_failed else "进入 kpatch 约束诊断。",
                evidence_paths=[
                    task_dir / "analysis" / "semantic_card.json",
                    task_dir / "analysis" / "trace" / "semantic_card_enrichment.json",
                ],
            ),
            self._stage_node(
                stage="diagnose",
                label="约束诊断",
                status="skipped" if source_failed else ("success" if (task_dir / "analysis" / "constraint_report.json").exists() else "pending"),
                current_effect="来源不可用，约束诊断未执行。" if source_failed else ("已输出热补丁约束和候选路线。" if (task_dir / "analysis" / "constraint_report.json").exists() else "尚未形成约束报告。"),
                missing_effect="未获得 patch，无法诊断 kpatch 约束。" if source_failed else ("无" if (task_dir / "analysis" / "constraint_report.json").exists() else "缺少 constraint_report.json。"),
                problem="source_unavailable" if source_failed else None,
                analysis="该阶段对齐 kpatch 限制，例如 fentry、init、静态数据和 ABI 风险。",
                next_action="先解决来源获取问题。" if source_failed else "进入改写规划。",
                evidence_paths=[task_dir / "analysis" / "constraint_report.json"],
            ),
            self._stage_node(
                stage="plan",
                label="改写规划",
                status="success" if attempt_dir and (attempt_dir / "rewrite" / "rewrite_plan.json").exists() else "pending",
                current_effect="已选择改写 recipe 和候选路径。" if attempt_dir and (attempt_dir / "rewrite" / "rewrite_plan.json").exists() else "尚未形成改写计划。",
                missing_effect="无" if attempt_dir and (attempt_dir / "rewrite" / "rewrite_plan.json").exists() else "缺少 rewrite_plan.json。",
                problem=None,
                analysis="规划层只选择路线，不直接代表构建成功。",
                next_action="输出 rewritten.patch 并执行 apply 预检查。",
                evidence_paths=[attempt_dir / "rewrite" / "rewrite_plan.json"] if attempt_dir else [],
            ),
            self._stage_node(
                stage="rewrite",
                label="补丁改写",
                status="success" if attempt_dir and (attempt_dir / "rewrite" / "rewritten.patch").exists() else "pending",
                current_effect="已输出 rewritten.patch 和改写留痕。" if attempt_dir and (attempt_dir / "rewrite" / "rewritten.patch").exists() else "尚未输出 rewritten.patch。",
                missing_effect="无" if attempt_dir and (attempt_dir / "rewrite" / "rewritten.patch").exists() else "缺少 rewritten.patch。",
                problem=str((latest_apply_precheck or {}).get("failure_type") or "") or None,
                analysis=str((latest_apply_precheck or {}).get("summary") or "改写阶段只说明补丁产物是否已生成。"),
                next_action="进入构建预检查或真实 kpatch-build。",
                evidence_paths=[
                    attempt_dir / "rewrite" / "rewritten.patch",
                    attempt_dir / "rewrite" / "apply_precheck.json",
                    attempt_dir / "rewrite" / "transformation_trace.json",
                ] if attempt_dir else [],
            ),
            self._build_stage_node(
                attempt_dir=attempt_dir,
                latest_attempt=latest_attempt,
                latest_failure=latest_failure,
                latest_build_summary=latest_build_summary,
                latest_failure_type=latest_failure_type,
                latest_build_exec_status=latest_build_exec_status,
                target_already_patched=target_already_patched,
            ),
            self._stage_node(
                stage="failure_analysis",
                label="失败归因",
                status="success" if latest_failure else ("skipped" if latest_attempt and latest_attempt.status == "built" else "pending"),
                current_effect="已形成结构化失败记录。" if latest_failure else "当前没有失败归因记录。",
                missing_effect="无" if latest_failure else "失败时应补齐 failure_record.json。",
                problem=latest_failure_type,
                analysis=str((latest_failure or {}).get("summary") or "失败归因阶段只读取主链失败证据。"),
                next_action="根据 failure_type 决定下一轮改写或环境修复。",
                evidence_paths=[attempt_dir / "logs" / "failure_record.json"] if attempt_dir else [source_failure_path],
            ),
            self._stage_node(
                stage="validate",
                label="验证",
                status="skipped" if source_failed else self._validation_stage_status(latest_attempt, latest_validation, target_already_patched),
                current_effect="来源不可用，未产出 .ko，动态验证未执行。" if source_failed else self._validation_current_effect(latest_validation, target_already_patched),
                missing_effect="未产出可加载模块，load/unload/smoke 未执行。" if source_failed else self._validation_missing_effect(latest_attempt, latest_validation, target_already_patched),
                problem=None if validation_status in {"", "passed", "pending"} else validation_status,
                analysis="验证阶段必须区分构建未产出模块、配置跳过、目标已修复导致跳过。",
                next_action="先解决来源获取问题。" if source_failed else "构建成功后补齐 load/unload/smoke/semantic_guard 证据。",
                evidence_paths=[
                    attempt_dir / "artifacts" / "validation_report.json",
                    attempt_dir / "artifacts" / "validation_matrix.json",
                    attempt_dir / "logs" / "load.log",
                    attempt_dir / "logs" / "unload.log",
                    attempt_dir / "logs" / "smoke.log",
                ] if attempt_dir else [],
            ),
            self._stage_node(
                stage="report",
                label="报告与回放",
                status="success" if report_complete else ("pending" if report_json_path.exists() else "pending"),
                current_effect="已生成结构化报告。" if report_complete else ("已有骨架报告，但缺少 attempt 或失败归因，不能视为完整闭环。" if report_json_path.exists() else "尚未生成最终报告。"),
                missing_effect="无" if report_complete else ("缺少主链证据，报告不完整。" if report_json_path.exists() else "缺少 report.json/report.md。"),
                problem=None if report_complete else ("incomplete_report" if report_json_path.exists() else None),
                analysis="报告阶段应复用主链结论，不重新判定业务状态。",
                next_action="用于演示、回放和阶段验收。" if report_complete else "先执行分析或补齐失败归因，再生成报告。",
                evidence_paths=[
                    task_dir / "reports" / "report.json",
                    task_dir / "reports" / "report.md",
                    task_dir / "reports" / "evaluation_summary.json",
                ],
            ),
        ]
        return self._linearize_stage_view(stage_nodes)

    def _build_stage_node(
        self,
        *,
        attempt_dir: Path | None,
        latest_attempt: Any | None,
        latest_failure: dict[str, Any] | None,
        latest_build_summary: dict[str, Any] | None,
        latest_failure_type: str | None,
        latest_build_exec_status: str | None,
        target_already_patched: bool,
    ) -> dict[str, Any]:
        """生成构建阶段节点"""

        if latest_attempt is None:
            if latest_failure_type == "source_unavailable":
                status = "skipped"
                current_effect = "来源不可用，构建阶段未执行。"
                missing_effect = "未获得可改写 patch，未执行 apply 预检查和 kpatch-build。"
                problem = "source_unavailable"
                analysis = str((latest_failure or {}).get("summary") or "没有可构建输入。")
                next_action = self._next_action_for_failure(latest_failure_type, latest_build_exec_status)
            else:
                status = "pending"
                current_effect = "尚未进入构建阶段。"
                missing_effect = "未执行 apply 预检查和 kpatch-build。"
                problem = None
                analysis = "没有 attempt 记录，不能判定构建结果。"
                next_action = "执行一轮尝试。"
        elif target_already_patched:
            status = "skipped"
            current_effect = "已完成目标源码状态判定。"
            missing_effect = "真实 kpatch-build 未执行，未产出 .ko。"
            problem = "target_already_patched"
            analysis = "目标已修复不是普通构建失败，页面应展示为构建未执行。"
            next_action = "切换未修复源码树或将样例标注为已修复态。"
        elif latest_attempt.status == "built":
            status = "success"
            current_effect = "真实 kpatch-build 已执行并形成构建成功记录。"
            missing_effect = "无" if latest_attempt.module_path else "模块产物路径缺失。"
            problem = None
            analysis = "构建成功后仍需验证阶段确认 load/unload/smoke。"
            next_action = "进入验证阶段。"
        elif latest_attempt.status == "failed":
            status = "failed"
            current_effect = "已形成构建或构建预检查失败证据。"
            missing_effect = "未产出可加载 .ko。"
            problem = latest_failure_type or "unknown"
            analysis = str((latest_failure or {}).get("summary") or (latest_build_summary or {}).get("summary") or "请查看 build.log。")
            next_action = self._next_action_for_failure(latest_failure_type, latest_build_exec_status)
        else:
            status = "pending"
            current_effect = "构建阶段尚未收口。"
            missing_effect = "缺少最终 build_summary 或 failure_record。"
            problem = latest_failure_type
            analysis = "当前 attempt 状态仍在中间态。"
            next_action = "等待本轮执行结束或补齐失败记录。"

        return self._stage_node(
            stage="build",
            label="构建",
            status=status,
            current_effect=current_effect,
            missing_effect=missing_effect,
            problem=problem,
            analysis=analysis,
            next_action=next_action,
            evidence_paths=[
                attempt_dir / "logs" / "build.log",
                attempt_dir / "artifacts" / "build_summary.json",
                attempt_dir / "artifacts" / "build_precheck.json",
            ] if attempt_dir else [],
        )

    def _linearize_stage_view(self, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """按主链首个失败阶段截断后续阶段展示，避免后处理产物被误读为成功"""

        failure_index = next((index for index, node in enumerate(nodes) if node.get("status") == "failed"), None)
        if failure_index is None:
            return nodes

        failed_node = nodes[failure_index]
        failed_label = str(failed_node.get("label") or failed_node.get("stage") or "前置阶段")
        failed_problem = str(failed_node.get("problem") or "blocked_by_previous_failure")
        failed_next_action = str(failed_node.get("next_action") or "先处理前置失败")
        linearized = nodes[: failure_index + 1]

        for node in nodes[failure_index + 1 :]:
            blocked_node = dict(node)
            blocked_node["status"] = "blocked"
            blocked_node["current_effect"] = f"主链已在{failed_label}阶段失败，本阶段未进入成功链路"
            blocked_node["missing_effect"] = "前置失败未解决，不能判定本阶段成功"
            blocked_node["problem"] = blocked_node.get("problem") or failed_problem
            blocked_node["analysis"] = "线性时间轴按首个失败阶段截断，后处理产物不计为阶段成功"
            blocked_node["next_action"] = failed_next_action
            linearized.append(blocked_node)

        return linearized

    def _stage_node(
        self,
        *,
        stage: str,
        label: str,
        status: str,
        current_effect: str,
        missing_effect: str,
        problem: str | None,
        analysis: str,
        next_action: str,
        evidence_paths: list[Path],
    ) -> dict[str, Any]:
        """统一阶段节点字段"""

        existing_paths = [path for path in evidence_paths if path.exists()]
        primary_path = existing_paths[0] if existing_paths else (evidence_paths[0] if evidence_paths else None)
        return {
            "stage": stage,
            "label": label,
            "status": status,
            "current_effect": current_effect,
            "missing_effect": missing_effect,
            "problem": problem,
            "analysis": analysis,
            "next_action": next_action,
            "evidence_paths": [self._path(path) for path in existing_paths],
            "primary_evidence_path": self._path(primary_path) if primary_path is not None else None,
            "path": self._path(primary_path) if primary_path is not None else None,
        }

    def _latest_failure_type(
        self,
        latest_attempt: Any | None,
        latest_failure: dict[str, Any] | None,
        latest_build_summary: dict[str, Any] | None,
        latest_apply_precheck: dict[str, Any] | None,
    ) -> str | None:
        """读取最近失败类型，真实构建执行后以最终构建结论优先"""

        build_exec_status = self._latest_build_exec_status(latest_attempt, latest_build_summary, latest_apply_precheck)
        if build_exec_status == "executed":
            for value in [
                (latest_build_summary or {}).get("failure_type"),
                latest_attempt.failure_type if latest_attempt is not None else None,
                (latest_failure or {}).get("failure_type"),
            ]:
                if value:
                    return str(value)
            return None

        for source in [latest_build_summary, latest_apply_precheck, latest_failure]:
            if source and source.get("target_state") == "target_already_patched":
                return "target_already_patched"
        if latest_attempt is not None and latest_attempt.target_state == "target_already_patched":
            return "target_already_patched"
        for source in [latest_failure, latest_build_summary, latest_apply_precheck]:
            value = (source or {}).get("failure_type")
            if value:
                return str(value)
        return latest_attempt.failure_type if latest_attempt is not None else None

    def _latest_target_state(
        self,
        latest_attempt: Any | None,
        latest_build_summary: dict[str, Any] | None,
        latest_apply_precheck: dict[str, Any] | None,
    ) -> str | None:
        """读取最近目标态结论"""

        build_exec_status = self._latest_build_exec_status(latest_attempt, latest_build_summary, latest_apply_precheck)
        if build_exec_status == "executed":
            return None

        target_state_sources = [latest_build_summary, latest_apply_precheck]
        for source in target_state_sources:
            value = (source or {}).get("target_state")
            if value:
                return str(value)
        return latest_attempt.target_state if latest_attempt is not None else None

    def _latest_build_exec_status(
        self,
        latest_attempt: Any | None,
        latest_build_summary: dict[str, Any] | None,
        latest_apply_precheck: dict[str, Any] | None,
    ) -> str | None:
        """读取最近构建执行状态"""

        value = (latest_build_summary or {}).get("build_exec_status")
        if value:
            return str(value)
        if latest_attempt is not None and latest_attempt.build_exec_status:
            return latest_attempt.build_exec_status
        value = (latest_apply_precheck or {}).get("build_exec_status")
        if value:
            return str(value)
        return None

    def _state_conflicts(
        self,
        *,
        latest_attempt: Any | None,
        latest_failure: dict[str, Any] | None,
        latest_apply_precheck: dict[str, Any] | None,
        latest_build_summary: dict[str, Any] | None,
    ) -> list[str]:
        """暴露历史产物或多层口径不一致，不在前端隐式掩盖"""

        observed = {
            "attempt": latest_attempt.failure_type if latest_attempt is not None else None,
            "failure_record": (latest_failure or {}).get("failure_type"),
            "apply_precheck": (latest_apply_precheck or {}).get("failure_type"),
            "build_summary": (latest_build_summary or {}).get("failure_type"),
        }
        present = {name: value for name, value in observed.items() if value}
        if len(set(present.values())) <= 1:
            return []
        return [f"{name}={value}" for name, value in present.items()]

    def _next_action_for_failure(self, failure_type: str | None, build_exec_status: str | None) -> str:
        """把失败类型映射成用户可执行的下一步"""

        if failure_type == "source_unavailable":
            return "该 CVE 没有解析到可下载的 stable/upstream patch 来源；请换有明确修复提交的 CVE，或补充来源映射后重试。"
        if failure_type == "patch_apply_failed":
            return "优先检查 rewritten.patch 与目标源码树上下文，必要时做 backport 适配。"
        if failure_type == "compile_failed" and build_exec_status == "executed":
            return "优先查看 build.log 和本地 kpatch 日志，区分编译错误、补丁输入格式和超时。"
        if failure_type == "kpatch_constraint":
            return "回到约束诊断和 Recipe 选择，避开 fentry、init、全局数据或 ABI 风险。"
        if failure_type in {"build_env_missing", "kernel_src_missing", "kernel_config_missing", "vmlinux_missing"}:
            return "先补齐构建环境、源码树、.config 或 vmlinux，再重跑。"
        return "查看 failure_record、build.log 和 harness_trace 后决定下一轮改写策略。"

    def _validation_stage_status(
        self,
        latest_attempt: Any | None,
        latest_validation: dict[str, Any] | None,
        target_already_patched: bool,
    ) -> str:
        """判定验证阶段展示状态"""

        if target_already_patched:
            return "skipped"
        raw_status = str((latest_validation or {}).get("status") or "")
        if raw_status == "passed":
            return "success"
        if raw_status == "failed":
            return "failed"
        if latest_attempt is not None and latest_attempt.status == "built":
            return "pending"
        return "pending"

    def _validation_current_effect(self, latest_validation: dict[str, Any] | None, target_already_patched: bool) -> str:
        """描述验证阶段当前效果"""

        if target_already_patched:
            return "目标已修复导致真实构建跳过，验证链未执行。"
        if latest_validation is None:
            return "尚未形成验证报告。"
        status = latest_validation.get("status")
        if status == "passed":
            return "验证报告已通过。"
        if status == "failed":
            return "验证报告已形成失败结论。"
        return "已有验证报告，但动态验证尚未完成。"

    def _validation_missing_effect(
        self,
        latest_attempt: Any | None,
        latest_validation: dict[str, Any] | None,
        target_already_patched: bool,
    ) -> str:
        """描述验证阶段缺口"""

        if target_already_patched:
            return "未产出 .ko，未执行 load/unload/smoke。"
        if latest_attempt is None or latest_attempt.status != "built":
            return "未产出可验证模块，load/unload/smoke 未执行。"
        if latest_validation is None:
            return "缺少 validation_report.json。"
        if latest_validation.get("status") != "passed":
            return "验证尚未通过。"
        return "无"

    def _relative_to_workspace(self, workspace_dir: Path, path: Path) -> str:
        """把产物绝对路径转成相对工作区路径"""

        resolved = Path(path).resolve()
        try:
            return resolved.relative_to(workspace_dir.resolve()).as_posix()
        except ValueError:
            return str(resolved)

    def _build_timeline(self, task_dir: Path, attempts: list[Any]) -> list[dict[str, Any]]:
        """根据产物落盘情况生成任务详情页的阶段时间线"""

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
                    "path": self._path(marker) if marker else None,
                }
            )
        return timeline

    def _path(self, value: Path | None) -> str | None:
        """把项目内路径转换成相对源码根目录表达"""

        return to_project_relative(self.context.project_root, value)

    def _load_fixture_catalog(self) -> list[dict[str, str | None]]:
        """从固定样例定义中加载任务到样例分组的映射"""

        fixtures_dir = (self.context.project_root / "evaluations" / "fixtures").resolve()
        if not fixtures_dir.exists():
            return []

        items: list[dict[str, str | None]] = []
        for fixture_path in sorted(fixtures_dir.glob("*.json")):
            try:
                payload = json.loads(fixture_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, list):
                continue
            for raw_item in payload:
                if not isinstance(raw_item, dict):
                    continue
                cve_id = raw_item.get("cve_id")
                if not cve_id:
                    continue
                items.append(
                    {
                        "fixture_id": str(raw_item.get("fixture_id") or ""),
                        "fixture_group": str(
                            raw_item.get("fixture_group") or raw_item.get("sample_group") or raw_item.get("group") or "default"
                        ).replace("-", "_"),
                        "cve_id": str(cve_id),
                        "target_kernel": str(raw_item.get("target_kernel")) if raw_item.get("target_kernel") else None,
                    }
                )
        return items

    def _resolve_fixture_binding(
        self,
        fixture_catalog: list[dict[str, str | None]],
        *,
        cve_id: str,
        target_kernel: str | None,
    ) -> dict[str, str | None] | None:
        """按 CVE 和目标内核把任务映射回固定样例定义"""

        exact_match: dict[str, str | None] | None = None
        fallback_match: dict[str, str | None] | None = None
        for item in fixture_catalog:
            if item["cve_id"] != cve_id:
                continue
            if item["target_kernel"] and target_kernel and item["target_kernel"] == target_kernel:
                exact_match = item
                break
            if fallback_match is None:
                fallback_match = item
        return exact_match or fallback_match

    def _normalize_datetime_filter(self, value: str | None) -> str | None:
        """把前端传入的时间筛选统一转成 SQLite 易比较的格式"""

        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.strftime("%Y-%m-%d %H:%M:%S")
