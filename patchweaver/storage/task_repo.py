"""任务索引读写"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from patchweaver.models.patch import PatchBundle
from patchweaver.models.task import MachineProfile, TaskContext
from patchweaver.storage.sqlite import connect_sqlite, initialize_sqlite_db
from patchweaver.utils.path_policy import resolve_project_path, to_project_relative


class TaskRepository:
    """负责任务主索引的落盘与读取"""

    def __init__(self, database_path: Path, project_root: Path | None = None) -> None:
        """保存数据库路径并确保基础表存在"""

        self.database_path = initialize_sqlite_db(database_path)
        self.project_root = project_root.resolve() if project_root is not None else None

    def next_task_id(self, now: datetime | None = None) -> str:
        """按日期生成下一个任务编号"""

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
        """写入一条新的任务记录"""

        with connect_sqlite(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO tasks(task_id, cve_id, target_kernel, target_kernel_source, profile_name, status, current_attempt, max_attempts, workspace_dir, environment_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.task_id,
                    task.cve_id,
                    task.target_kernel,
                    task.target_kernel_source,
                    task.profile_name,
                    task.status,
                    task.current_attempt,
                    task.max_attempts,
                    self._store_path(task.workspace_dir),
                    self._store_environment(task.machine_profile),
                    task.created_at.isoformat(),
                    task.updated_at.isoformat(),
                ),
            )
            connection.commit()
        return task

    def get_task(self, task_id: str) -> TaskContext | None:
        """按任务编号读取任务记录"""

        with connect_sqlite(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT task_id, cve_id, target_kernel, target_kernel_source, profile_name, status, current_attempt, max_attempts, workspace_dir, environment_json, created_at, updated_at
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
            target_kernel_source=row["target_kernel_source"],
            profile_name=row["profile_name"],
            status=row["status"],
            current_attempt=row["current_attempt"],
            max_attempts=row["max_attempts"],
            workspace_dir=self._load_path(row["workspace_dir"]),
            machine_profile=self._load_environment(row["environment_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def list_tasks(self, limit: int = 20) -> list[TaskContext]:
        """读取最近创建的任务列表"""

        with connect_sqlite(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT task_id, cve_id, target_kernel, target_kernel_source, profile_name, status, current_attempt, max_attempts, workspace_dir, environment_json, created_at, updated_at
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
                target_kernel_source=row["target_kernel_source"],
                profile_name=row["profile_name"],
                status=row["status"],
                current_attempt=row["current_attempt"],
                max_attempts=row["max_attempts"],
                workspace_dir=self._load_path(row["workspace_dir"]),
                machine_profile=self._load_environment(row["environment_json"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
            for row in rows
        ]

    def update_task_status(self, task_id: str, *, status: str, current_attempt: int | None = None) -> None:
        """更新任务状态和当前尝试轮"""

        updated_at = datetime.now(timezone.utc).isoformat()
        with connect_sqlite(self.database_path) as connection:
            connection.execute(
                """
                UPDATE tasks
                SET status = ?,
                    current_attempt = COALESCE(?, current_attempt),
                    updated_at = ?
                WHERE task_id = ?
                """,
                (status, current_attempt, updated_at, task_id),
            )
            connection.commit()

    def task_exists(self, task_id: str) -> bool:
        """判断任务是否已经存在"""

        with connect_sqlite(self.database_path) as connection:
            row = connection.execute("SELECT 1 FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        return row is not None

    def save_patch_bundle(self, bundle: PatchBundle) -> PatchBundle:
        """保存任务对应的 PatchBundle"""

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
                    self._store_path(bundle.raw_patch_path),
                    self._store_path(bundle.normalized_patch_path),
                    json.dumps([item.model_dump() for item in bundle.source_evidence], ensure_ascii=False),
                ),
            )
            connection.commit()
        return bundle

    def get_latest_patch_bundle(self, task_id: str) -> PatchBundle | None:
        """读取任务最近一次保存的 PatchBundle"""

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
            raw_patch_path=self._load_optional_path(row["raw_patch_path"]),
            normalized_patch_path=self._load_optional_path(row["normalized_patch_path"]),
            source_evidence=json.loads(row["source_evidence_json"] or "[]"),
        )

    def _store_path(self, path: Path | None) -> str | None:
        """把项目内路径转换成持久化用的相对路径"""

        return to_project_relative(self.project_root, path)

    def _load_path(self, value: str) -> Path:
        """把数据库中的路径恢复为当前机器可用的路径对象"""

        resolved = resolve_project_path(self.project_root, value)
        if resolved is None:
            raise ValueError("任务路径不能为空。")
        return resolved

    def _load_optional_path(self, value: str | None) -> Path | None:
        """恢复可选路径字段"""

        return resolve_project_path(self.project_root, value)

    def _store_environment(self, machine_profile: MachineProfile | None) -> str | None:
        """把机器环境快照序列化到数据库"""

        if machine_profile is None:
            return None
        return json.dumps(machine_profile.model_dump(mode="json"), ensure_ascii=False)

    def _load_environment(self, payload: str | None) -> MachineProfile | None:
        """恢复机器环境快照"""

        if not payload:
            return None
        return MachineProfile.model_validate_json(payload)
