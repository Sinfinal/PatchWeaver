"""任务查询与动作执行服务"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from patchweaver.api.deps import ApiContext
from patchweaver.config.resolver import resolve_runtime
from patchweaver.harness.workspace_guard import WorkspaceGuard
from patchweaver.models.task import TaskContext
from patchweaver.observability.run_logger import RunLogger
from patchweaver.runtime_inspector import resolve_task_binding
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
            "task": self._task_payload(task),
            "next_attempt_dir": self._path(task_dir / "attempts" / "001"),
            "prepared_attempt_dir": self._path(task_dir / "attempts" / "001"),
            "request_path": self._path(request_path),
        }

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
        if latest_attempt is not None:
            attempt_dir = task_dir / "attempts" / f"{latest_attempt.attempt_no:03d}"
            latest_failure_path = attempt_dir / "logs" / "failure_record.json"
            latest_validation_path = attempt_dir / "artifacts" / "validation_report.json"
            latest_trace_path = attempt_dir / "trace" / "harness_trace.json"
            latest_rewrite_plan_path = attempt_dir / "rewrite" / "rewrite_plan.json"

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

        return {
            # task 是顶部摘要
            # analysis、attempts、reports、replay 对应页面里的四块主视图
            "task": self._task_payload(task, latest_attempt=latest_attempt),
            "patch_bundle": self._load_json(task_dir / "input" / "patch_bundle.json"),
            "analysis": {
                "semantic_card_path": self._path(task_dir / "analysis" / "semantic_card.json"),
                "semantic_card_enrichment_path": self._path(task_dir / "analysis" / "trace" / "semantic_card_enrichment.json"),
                "constraint_report_path": self._path(task_dir / "analysis" / "constraint_report.json"),
                "context_bundle_path": self._path(task_dir / "analysis" / "context" / "context_bundle.json"),
                "analysis_trace_path": self._path(task_dir / "analysis" / "trace" / "analysis_trace.json"),
            },
            "attempts": [self._attempt_payload(task_dir, item) for item in attempts],
            "latest_failure": self._load_json(latest_failure_path),
            "latest_validation": self._load_json(latest_validation_path),
            "latest_trace": self._load_json(latest_trace_path),
            "latest_rewrite_plan": self._load_json(latest_rewrite_plan_path),
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

    def _task_payload(self, task: TaskContext, latest_attempt=None) -> dict[str, Any]:
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
            "latest_failure_type": latest_attempt.failure_type if latest_attempt is not None else None,
            "latest_build_exec_status": latest_attempt.build_exec_status if latest_attempt is not None else None,
            "latest_target_state": latest_attempt.target_state if latest_attempt is not None else None,
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
