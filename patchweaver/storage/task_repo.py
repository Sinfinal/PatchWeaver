"""任务索引读写。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from patchweaver.models.patch import PatchBundle
from patchweaver.models.task import TaskContext
from patchweaver.storage.sqlite import connect_sqlite, initialize_sqlite_db


class TaskRepository:
    """负责任务主索引的落盘与读取。"""

    def __init__(self, database_path: Path) -> None:
        """保存数据库路径并确保基础表存在。"""

        self.database_path = initialize_sqlite_db(database_path)

    def next_task_id(self, now: datetime | None = None) -> str:
        """按日期生成下一个任务编号。"""

        current = now or datetime.now()
        prefix = f"TASK-{current:%Y%m%d}-"
        with connect_sqlite(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT task_id
                FROM tasks
                WHERE task_id LIKE ?
                ORDER BY task_id DESC
                LIMIT 1
                """,
                (f"{prefix}%",),
            ).fetchone()

        if row is None:
            return f"{prefix}001"

        serial = int(str(row["task_id"]).split("-")[-1]) + 1
        return f"{prefix}{serial:03d}"

    def create_task(self, task: TaskContext) -> TaskContext:
        """写入一条新的任务记录。"""

        with connect_sqlite(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO tasks(task_id, cve_id, target_kernel, status, current_attempt, max_attempts, workspace_dir, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.task_id,
                    task.cve_id,
                    task.target_kernel,
                    task.status,
                    task.current_attempt,
                    task.max_attempts,
                    str(task.workspace_dir),
                    task.created_at.isoformat(),
                    task.updated_at.isoformat(),
                ),
            )
            connection.commit()
        return task

    def get_task(self, task_id: str) -> TaskContext | None:
        """按任务编号读取任务记录。"""

        with connect_sqlite(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT task_id, cve_id, target_kernel, status, current_attempt, max_attempts, workspace_dir, created_at, updated_at
                FROM tasks
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()

        if row is None:
            return None

        return TaskContext(
            task_id=row["task_id"],
            cve_id=row["cve_id"],
            target_kernel=row["target_kernel"],
            status=row["status"],
            current_attempt=row["current_attempt"],
            max_attempts=row["max_attempts"],
            workspace_dir=Path(row["workspace_dir"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def list_tasks(self, limit: int = 20) -> list[TaskContext]:
        """读取最近创建的任务列表。"""

        with connect_sqlite(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT task_id, cve_id, target_kernel, status, current_attempt, max_attempts, workspace_dir, created_at, updated_at
                FROM tasks
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            TaskContext(
                task_id=row["task_id"],
                cve_id=row["cve_id"],
                target_kernel=row["target_kernel"],
                status=row["status"],
                current_attempt=row["current_attempt"],
                max_attempts=row["max_attempts"],
                workspace_dir=Path(row["workspace_dir"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
            for row in rows
        ]

    def update_task_status(self, task_id: str, *, status: str, current_attempt: int | None = None) -> None:
        """更新任务状态和当前尝试轮。"""

        with connect_sqlite(self.database_path) as connection:
            connection.execute(
                """
                UPDATE tasks
                SET status = ?,
                    current_attempt = COALESCE(?, current_attempt),
                    updated_at = CURRENT_TIMESTAMP
                WHERE task_id = ?
                """,
                (status, current_attempt, task_id),
            )
            connection.commit()

    def task_exists(self, task_id: str) -> bool:
        """判断任务是否已经存在。"""

        with connect_sqlite(self.database_path) as connection:
            row = connection.execute("SELECT 1 FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        return row is not None

    def save_patch_bundle(self, bundle: PatchBundle) -> PatchBundle:
        """保存任务对应的 PatchBundle。"""

        with connect_sqlite(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO patch_bundles(task_ref, upstream_commit, stable_commit, commit_message, affected_files_json, raw_patch_path, normalized_patch_path, source_evidence_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bundle.task_id,
                    bundle.upstream_commit,
                    bundle.stable_commit,
                    bundle.commit_message,
                    json.dumps(bundle.affected_files, ensure_ascii=False),
                    str(bundle.raw_patch_path) if bundle.raw_patch_path else None,
                    str(bundle.normalized_patch_path) if bundle.normalized_patch_path else None,
                    json.dumps([item.model_dump() for item in bundle.source_evidence], ensure_ascii=False),
                ),
            )
            connection.commit()
        return bundle

    def get_latest_patch_bundle(self, task_id: str) -> PatchBundle | None:
        """读取任务最近一次保存的 PatchBundle。"""

        with connect_sqlite(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT task_ref, upstream_commit, stable_commit, commit_message, affected_files_json, raw_patch_path, normalized_patch_path, source_evidence_json
                FROM patch_bundles
                WHERE task_ref = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (task_id,),
            ).fetchone()

        if row is None:
            return None

        return PatchBundle(
            task_id=row["task_ref"],
            cve_id=self.get_task(task_id).cve_id if self.get_task(task_id) else "",
            upstream_commit=row["upstream_commit"],
            stable_commit=row["stable_commit"],
            commit_message=row["commit_message"],
            affected_files=json.loads(row["affected_files_json"] or "[]"),
            raw_patch_path=Path(row["raw_patch_path"]) if row["raw_patch_path"] else None,
            normalized_patch_path=Path(row["normalized_patch_path"]) if row["normalized_patch_path"] else None,
            source_evidence=json.loads(row["source_evidence_json"] or "[]"),
        )
