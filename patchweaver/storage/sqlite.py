"""SQLite 初始化与基础建表逻辑。"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "0.2.0"

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
    profile_name TEXT,
    status TEXT NOT NULL DEFAULT 'created',
    current_attempt INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    workspace_dir TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS patch_bundles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_ref TEXT NOT NULL,
    upstream_commit TEXT,
    stable_commit TEXT,
    commit_message TEXT,
    affected_files_json TEXT,
    raw_patch_path TEXT,
    normalized_patch_path TEXT,
    source_evidence_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(task_ref) REFERENCES tasks(task_id) ON DELETE CASCADE
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

CREATE TABLE IF NOT EXISTS attempt_states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_ref TEXT NOT NULL,
    attempt_no INTEGER NOT NULL,
    stage TEXT NOT NULL,
    remaining_budget_json TEXT,
    disabled_strategies_json TEXT,
    termination_reason TEXT,
    payload_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(task_ref) REFERENCES tasks(task_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS failure_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_ref TEXT NOT NULL,
    attempt_ref TEXT NOT NULL,
    stage_name TEXT NOT NULL,
    failure_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    evidence_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(task_ref) REFERENCES tasks(task_id) ON DELETE CASCADE
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

CREATE TABLE IF NOT EXISTS evidence_spans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_ref TEXT NOT NULL,
    attempt_ref TEXT,
    evidence_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_path TEXT NOT NULL,
    excerpt TEXT NOT NULL,
    start_line INTEGER,
    end_line INTEGER,
    score REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(task_ref) REFERENCES tasks(task_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS harness_traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL UNIQUE,
    task_ref TEXT NOT NULL,
    attempt_ref TEXT,
    trace_path TEXT,
    summary_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(task_ref) REFERENCES tasks(task_id) ON DELETE CASCADE
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

CREATE INDEX IF NOT EXISTS idx_tasks_cve_id ON tasks(cve_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_attempts_task_id ON attempts(task_id);
CREATE INDEX IF NOT EXISTS idx_attempts_status ON attempts(status);
CREATE INDEX IF NOT EXISTS idx_attempts_failure_type ON attempts(failure_type);
CREATE INDEX IF NOT EXISTS idx_failure_records_type ON failure_records(failure_type);
CREATE INDEX IF NOT EXISTS idx_artifacts_type ON artifacts(artifact_type);
"""


def _utc_now() -> str:
    """返回当前 UTC 时间字符串。"""

    return datetime.now(timezone.utc).isoformat()


def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    """读取指定表的现有字段。"""

    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1] for row in rows}


def _ensure_column(connection: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
    """在旧库缺少字段时追加兼容列。"""

    columns = _table_columns(connection, table_name)
    if column_name in columns:
        return
    connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def connect_sqlite(database_path: Path) -> sqlite3.Connection:
    """创建启用行对象的 SQLite 连接。"""

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_sqlite_db(database_path: Path) -> Path:
    """初始化 SQLite 文件和首批基础表。"""

    # 这个入口同时承担“首装建库”和“旧库补字段”两件事，CLI 各命令都可以安全复用。
    # 先确保数据库目录存在，避免首次初始化时因为父目录缺失失败。
    database_path.parent.mkdir(parents=True, exist_ok=True)

    with connect_sqlite(database_path) as connection:
        # 初始化阶段直接执行整套 schema，重复执行也不会破坏已有表结构。
        connection.executescript(SCHEMA_SQL)

        # 后续阶段新增字段时，优先走这里做轻量兼容，避免频繁重写整套建表 SQL。
        # 旧版本库需要补齐后续阶段新增的关键字段。
        _ensure_column(connection, "tasks", "profile_name", "TEXT")
        _ensure_column(connection, "attempts", "attempt_id", "TEXT")
        _ensure_column(connection, "attempts", "rewritten_patch_path", "TEXT")
        _ensure_column(connection, "attempts", "summary_json", "TEXT")
        _ensure_column(connection, "validation_records", "load_result_json", "TEXT")
        _ensure_column(connection, "validation_records", "unload_result_json", "TEXT")
        _ensure_column(connection, "validation_records", "smoke_result_json", "TEXT")
        _ensure_column(connection, "validation_records", "semantic_guard_result_json", "TEXT")
        _ensure_column(connection, "validation_records", "semantic_precheck_result_json", "TEXT")
        _ensure_column(connection, "validation_records", "selftest_result_json", "TEXT")
        _ensure_column(connection, "validation_records", "regression_result_json", "TEXT")
        _ensure_column(connection, "validation_records", "validation_matrix_json", "TEXT")
        _ensure_column(connection, "validation_records", "validation_intensity", "TEXT")

        # 版本和初始化时间每次都刷新一遍，查库状态时会方便很多。
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
            ("initialized_at", _utc_now()),
        )
        # 首版先显式提交，保证 CLI 初始化结束后数据库状态已经落盘。
        connection.commit()

    return database_path.resolve()
