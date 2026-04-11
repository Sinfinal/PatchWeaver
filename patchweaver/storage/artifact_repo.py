"""产物索引读写。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from patchweaver.models.harness import ArtifactRef
from patchweaver.storage.sqlite import connect_sqlite, initialize_sqlite_db


class ArtifactRepository:
    """负责报告、日志和构建产物的索引。"""

    def __init__(self, database_path: Path) -> None:
        """保存数据库路径并确保基础表存在。"""

        self.database_path = initialize_sqlite_db(database_path)

    def _task_row_id(self, task_id: str) -> int:
        """读取任务在数据库中的内部主键。"""

        with connect_sqlite(self.database_path) as connection:
            row = connection.execute("SELECT id FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            raise ValueError(f"任务不存在：{task_id}")
        return int(row["id"])

    def _attempt_row_id(self, attempt_id: str | None) -> int | None:
        """读取尝试轮在数据库中的内部主键。"""

        if attempt_id is None:
            return None

        with connect_sqlite(self.database_path) as connection:
            row = connection.execute("SELECT id FROM attempts WHERE attempt_id = ?", (attempt_id,)).fetchone()
        if row is None:
            return None
        return int(row["id"])

    def add_artifact(
        self,
        *,
        task_id: str,
        artifact_type: str,
        artifact_path: Path,
        attempt_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Path:
        """登记一条产物索引。"""

        with connect_sqlite(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO artifacts(task_id, attempt_id, artifact_type, artifact_path, metadata_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    self._task_row_id(task_id),
                    self._attempt_row_id(attempt_id),
                    artifact_type,
                    str(artifact_path),
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
            connection.commit()
        return artifact_path

    def list_artifacts(self, task_id: str) -> list[ArtifactRef]:
        """读取任务的产物索引。"""

        with connect_sqlite(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT artifact_type, artifact_path, metadata_json
                FROM artifacts
                JOIN tasks ON artifacts.task_id = tasks.id
                WHERE tasks.task_id = ?
                ORDER BY artifacts.id ASC
                """,
                (task_id,),
            ).fetchall()

        artifacts: list[ArtifactRef] = []
        for row in rows:
            metadata = json.loads(row["metadata_json"] or "{}")
            artifacts.append(
                ArtifactRef(
                    artifact_type=row["artifact_type"],
                    artifact_path=Path(row["artifact_path"]),
                    summary=str(metadata.get("summary", "")),
                )
            )
        return artifacts
