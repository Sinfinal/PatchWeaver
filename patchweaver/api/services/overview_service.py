"""总览页查询服务"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from patchweaver.api.deps import ApiContext
from patchweaver.api.services.log_service import LogService
from patchweaver.builder.orchestrator import BuildOrchestrator
from patchweaver.reporter.release_service import ReleaseService
from patchweaver.storage.sqlite import connect_sqlite
from patchweaver.utils.path_policy import to_project_relative


class OverviewService:
    """负责汇总首页需要的状态指标"""

    def __init__(self, context: ApiContext) -> None:
        """保存 API 共享上下文"""

        self.context = context
        self.log_service = LogService(context)

    def get_overview(self) -> dict[str, Any]:
        """汇总总览页需要的卡片、摘要和事件数据"""

        database_path = self.context.runtime.database_path
        # 首页不是简单读一张表
        # 这里把构建环境、交付快照、阶段评测和任务状态一起收拢成一份响应
        build_env = BuildOrchestrator(self.context.build_config).probe_environment()
        release_snapshot = ReleaseService(
            runtime=self.context.runtime,
            build_config=self.context.build_config,
            logging_config=self.context.logging_config,
            models_config=self.context.models_config,
            task_repo=self.context.task_repo,
            attempt_repo=self.context.attempt_repo,
            artifact_repo=self.context.artifact_repo,
        ).snapshot()
        evaluation_summaries = self._load_evaluation_summaries()
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

        # metrics 这一层尽量只放首页卡片直接会用到的聚合值
        # 明细项放到 recent_tasks 和 distribution，避免接口层级越长越乱
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
                "latest_evaluation_summary": self._path(Path(latest_evaluation["artifact_path"])) if latest_evaluation is not None else None,
                "delivery_ready": release_snapshot.get("final_gate_status") == "passed",
                "selected_model": self.context.models_config.delivery_model,
            },
            "release": release_snapshot,
            "evaluation_summaries": evaluation_summaries,
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

    def _load_evaluation_summaries(self) -> list[dict[str, Any]]:
        """读取阶段评测摘要，供总览页直接展示"""

        evaluations_dir = self.context.runtime.data_dir / "evaluations"
        if not evaluations_dir.exists():
            return []

        preferred_order = {
            "challenge_dev": 0,
            "holdout": 1,
            "contest_samples": 2,
        }
        summary_items: list[dict[str, Any]] = []

        # 第三阶段以后，总览页需要能直接看到固定样例和 holdout 的阶段结果，
        # 这里统一从 data/evaluations 下收拢，避免前端自己再去猜目录结构
        for summary_path in sorted(evaluations_dir.glob("*/summary.json")):
            payload = self._read_json(summary_path)
            if not isinstance(payload, dict):
                continue

            fixture_name = str(payload.get("fixture_name") or summary_path.parent.name)
            summary_items.append(
                {
                    "fixture_name": fixture_name,
                    "total_fixtures": int(payload.get("total_fixtures", 0) or 0),
                    "matched_fixtures": int(payload.get("matched_fixtures", 0) or 0),
                    "missing_fixtures": int(payload.get("missing_fixtures", 0) or 0),
                    "success_count": int(payload.get("success_count", 0) or 0),
                    "success_rate": float(payload.get("success_rate", 0.0) or 0.0),
                    "average_attempts": float(payload.get("average_attempts", 0.0) or 0.0),
                    "failure_distribution": payload.get("failure_distribution") or {},
                    "summary_json_path": self._path(summary_path),
                    "summary_md_path": self._path(summary_path.with_name("summary.md")),
                    "updated_at": summary_path.stat().st_mtime,
                    "sort_order": preferred_order.get(fixture_name, 99),
                }
            )

        summary_items.sort(
            key=lambda item: (
                int(item["sort_order"]),
                -float(item["updated_at"]),
                str(item["fixture_name"]),
            )
        )
        for item in summary_items:
            item.pop("sort_order", None)
            item["updated_at"] = self._format_timestamp(float(item["updated_at"]))
        return summary_items

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        """安全读取 JSON 文件"""

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _format_timestamp(self, value: float) -> str:
        """把文件修改时间转成展示友好的字符串"""

        return datetime.fromtimestamp(value).isoformat()

    def _count(self, connection, sql: str) -> int:
        """执行单值计数查询"""

        row = connection.execute(sql).fetchone()
        return int(row[0]) if row is not None else 0

    def _path(self, value: Path | None) -> str | None:
        """把项目内路径转换成相对源码根目录表达"""

        project_root = getattr(self.context, "project_root", self.context.runtime.project_root)
        return to_project_relative(project_root, value)
