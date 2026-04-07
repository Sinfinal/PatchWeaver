"""SQLite 初始化与基础建表逻辑。"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "0.1.0"

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL UNIQUE,
    cve_id TEXT NOT NULL,
    target_kernel TEXT,
    status TEXT NOT NULL DEFAULT 'created',
    current_attempt INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    workspace_dir TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    attempt_no INTEGER NOT NULL,
    candidate_id TEXT,
    status TEXT NOT NULL,
    failure_type TEXT,
    patch_path TEXT,
    build_log_path TEXT,
    module_path TEXT,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS build_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id INTEGER NOT NULL,
    builder TEXT NOT NULL DEFAULT 'kpatch-build',
    status TEXT NOT NULL,
    exit_code INTEGER,
    log_path TEXT,
    duration_sec REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(attempt_id) REFERENCES attempts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS validation_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    load_ok INTEGER NOT NULL DEFAULT 0,
    unload_ok INTEGER NOT NULL DEFAULT 0,
    smoke_ok INTEGER NOT NULL DEFAULT 0,
    regression_ok INTEGER NOT NULL DEFAULT 0,
    summary TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(attempt_id) REFERENCES attempts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    attempt_id INTEGER,
    artifact_type TEXT NOT NULL,
    artifact_path TEXT NOT NULL,
    metadata_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    FOREIGN KEY(attempt_id) REFERENCES attempts(id) ON DELETE SET NULL
);
"""


def initialize_sqlite_db(database_path: Path) -> Path:
    """初始化 SQLite 文件和首批基础表。"""

    # 先确保数据库目录存在，避免首次初始化时因为父目录缺失失败。
    database_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(database_path) as connection:
        # 初始化阶段直接执行整套 schema，重复执行也不会破坏已有表结构。
        connection.executescript(SCHEMA_SQL)
        # schema_meta 先记录版本和初始化时间，后续做迁移和排错都要用到。
        connection.execute(
            """
            INSERT INTO schema_meta(key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            ("schema_version", SCHEMA_VERSION),
        )
        connection.execute(
            """
            INSERT INTO schema_meta(key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            ("initialized_at", datetime.now(timezone.utc).isoformat()),
        )
        # 首版先显式提交，保证 CLI 初始化结束后数据库状态已经落盘。
        connection.commit()

    return database_path.resolve()
