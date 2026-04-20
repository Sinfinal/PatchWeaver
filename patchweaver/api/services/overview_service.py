"""总览页查询服务。"""

from __future__ import annotations

from typing import Any

from patchweaver.api.deps import ApiContext
from patchweaver.api.services.log_service import LogService
from patchweaver.builder.orchestrator import BuildOrchestrator
from patchweaver.storage.sqlite import connect_sqlite


class OverviewService:
    """负责汇总首页需要的状态指标。"""

    def __init__(self, context: ApiContext) -> None:
        """保存 API 共享上下文。"""

        self.context = context
        self.log_service = LogService(context)

    def get_overview(self) -> dict[str, Any]:
        """汇总总览页需要的卡片、摘要和事件数据。"""

        database_path = self.context.runtime.database_path
        build_env = BuildOrchestrator(self.context.build_config).probe_environment()
        with connect_sqlite(database_path) as connection:
            total_tasks = self._count(connection, "SELECT COUNT(*) FROM tasks")
            failed_tasks = self._count(connection, "SELECT COUNT(*) FROM tasks WHERE status = 'failed'")
            success_tasks = self._count(connection, "SELECT COUNT(*) FROM tasks WHERE status IN ('built', 'reported', 'succeeded')")
            running_tasks = self._count(
                connection,
                "SELECT COUNT(*) FROM tasks WHERE status IN ('created', 'analyzed', 'running', 'building', 'validating')",
            )
            recent_tasks = connection.execute(
                """
                SELECT task_id, cve_id, target_kernel, status, current_attempt, max_attempts, updated_at
                FROM tasks
                ORDER BY updated_at DESC
                LIMIT 6
                """
            ).fetchall()
            failure_distribution = connection.execute(
                """
                SELECT failure_type, COUNT(*) AS total
                FROM failure_records
                GROUP BY failure_type
                ORDER BY total DESC, failure_type ASC
                LIMIT 8
                """
            ).fetchall()
            validation_distribution = connection.execute(
                """
                SELECT status, COUNT(*) AS total
                FROM validation_records
                GROUP BY status
                ORDER BY total DESC, status ASC
                """
            ).fetchall()
            latest_evaluation = connection.execute(
                """
                SELECT artifact_path
                FROM artifacts
                WHERE artifact_type = 'evaluation_summary'
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()

        finished_tasks = success_tasks + failed_tasks
        success_rate = round((success_tasks / finished_tasks) * 100, 2) if finished_tasks else 0.0

        return {
            "metrics": {
                "total_tasks": total_tasks,
                "running_tasks": running_tasks,
                "success_tasks": success_tasks,
                "failed_tasks": failed_tasks,
                "success_rate": success_rate,
                "build_backend": build_env["backend"],
                "build_ready": bool(build_env.get("builder_ok") and build_env.get("selected_source_ok") and build_env.get("config_ok")),
                "validation_passed": next((row["total"] for row in validation_distribution if row["status"] == "passed"), 0),
                "validation_failed": next((row["total"] for row in validation_distribution if row["status"] == "failed"), 0),
                "latest_evaluation_summary": latest_evaluation["artifact_path"] if latest_evaluation is not None else None,
            },
            "recent_tasks": [
                {
                    "task_id": row["task_id"],
                    "cve_id": row["cve_id"],
                    "target_kernel": row["target_kernel"],
                    "status": row["status"],
                    "current_attempt": row["current_attempt"],
                    "max_attempts": row["max_attempts"],
                    "updated_at": row["updated_at"],
                }
                for row in recent_tasks
            ],
            "failure_distribution": [
                {"failure_type": row["failure_type"] or "unknown", "total": row["total"]} for row in failure_distribution
            ],
            "validation_distribution": [
                {"status": row["status"], "total": row["total"]} for row in validation_distribution
            ],
            "events": self.log_service.get_events(limit=12),
            "logs_tail": self.log_service.tail_logs(limit=40),
        }

    def _count(self, connection, sql: str) -> int:
        """执行单值计数查询。"""

        row = connection.execute(sql).fetchone()
        return int(row[0]) if row is not None else 0
