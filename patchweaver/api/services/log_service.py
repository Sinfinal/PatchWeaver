"""日志与事件读取服务。"""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any

from patchweaver.api.deps import ApiContext
from patchweaver.storage.sqlite import connect_sqlite


class LogService:
    """负责读取系统日志和近期事件。"""

    def __init__(self, context: ApiContext) -> None:
        """保存 API 共享上下文。"""

        self.context = context

    def get_events(self, *, limit: int = 40) -> list[dict[str, Any]]:
        """从任务、尝试轮和失败记录中拼出一条简化事件流。"""

        database_path = self.context.runtime.database_path
        events: list[dict[str, Any]] = []
        with connect_sqlite(database_path) as connection:
            task_rows = connection.execute(
                """
                SELECT task_id, cve_id, status, created_at, updated_at
                FROM tasks
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            attempt_rows = connection.execute(
                """
                SELECT tasks.task_id AS task_ref, attempts.attempt_id, attempts.attempt_no, attempts.status,
                       attempts.failure_type, attempts.finished_at
                FROM attempts
                JOIN tasks ON attempts.task_id = tasks.id
                ORDER BY attempts.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            failure_rows = connection.execute(
                """
                SELECT task_ref, attempt_ref, stage_name, failure_type, summary, created_at
                FROM failure_records
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        for row in task_rows:
            events.append(
                {
                    "timestamp": row["updated_at"] or row["created_at"],
                    "kind": "task",
                    "title": f"{row['task_id']} 状态更新为 {row['status']}",
                    "detail": row["cve_id"],
                    "task_id": row["task_id"],
                }
            )
        for row in attempt_rows:
            events.append(
                {
                    "timestamp": row["finished_at"],
                    "kind": "attempt",
                    "title": f"{row['attempt_id']} 执行结果：{row['status']}",
                    "detail": row["failure_type"] or "无失败类型",
                    "task_id": row["task_ref"],
                }
            )
        for row in failure_rows:
            events.append(
                {
                    "timestamp": row["created_at"],
                    "kind": "failure",
                    "title": f"{row['task_ref']} 失败归因：{row['failure_type']}",
                    "detail": row["summary"],
                    "task_id": row["task_ref"],
                }
            )

        return sorted(
            [item for item in events if item["timestamp"]],
            key=lambda item: item["timestamp"],
            reverse=True,
        )[:limit]

    def tail_logs(self, *, limit: int = 120) -> dict[str, Any]:
        """返回系统日志和最近构建日志的尾部内容。"""

        system_log_path = (self.context.project_root / self.context.logging_config.file_path).resolve()
        jsonl_log_path = (self.context.project_root / self.context.logging_config.jsonl_path).resolve()
        latest_build_log = self._latest_build_log()
        return {
            "system_log": self._tail_file(system_log_path, limit),
            "jsonl_log": self._tail_file(jsonl_log_path, limit) if self.context.logging_config.enable_jsonl else None,
            "latest_build_log": self._tail_file(latest_build_log, limit) if latest_build_log else None,
            "paths": {
                "system_log": str(system_log_path),
                "jsonl_log": str(jsonl_log_path) if self.context.logging_config.enable_jsonl else None,
                "latest_build_log": str(latest_build_log) if latest_build_log else None,
            },
        }

    def _latest_build_log(self) -> Path | None:
        """定位最近一条带日志路径的尝试轮。"""

        with connect_sqlite(self.context.runtime.database_path) as connection:
            row = connection.execute(
                """
                SELECT build_log_path
                FROM attempts
                WHERE build_log_path IS NOT NULL
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None or not row["build_log_path"]:
            return None
        return Path(row["build_log_path"])

    def _tail_file(self, path: Path, limit: int) -> dict[str, Any]:
        """读取文本文件尾部，避免一次把大日志全部打到页面。"""

        if not path.exists():
            return {"path": str(path), "exists": False, "lines": []}
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            lines = list(deque(handle, maxlen=limit))
        return {
            "path": str(path),
            "exists": True,
            "lines": [line.rstrip("\n") for line in lines],
        }
