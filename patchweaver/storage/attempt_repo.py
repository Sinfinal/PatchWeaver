"""尝试轮相关数据读写"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from patchweaver.models.attempt import AttemptRecord, AttemptState, FailureRecord
from patchweaver.models.evidence import EvidenceSpan
from patchweaver.models.harness import HarnessTrace
from patchweaver.models.validation import ValidationReport
from patchweaver.storage.sqlite import connect_sqlite, initialize_sqlite_db
from patchweaver.utils.path_policy import relativize_payload, resolve_project_path, to_project_relative


class AttemptRepository:
    """负责单轮尝试、失败归因和 trace 的落盘"""

    def __init__(self, database_path: Path, project_root: Path | None = None) -> None:
        """保存数据库路径并确保表结构存在"""

        self.database_path = initialize_sqlite_db(database_path)
        self.project_root = project_root.resolve() if project_root is not None else None

    def _task_row_id(self, task_id: str) -> int:
        """读取任务在数据库里的内部主键"""

        with connect_sqlite(self.database_path) as connection:
            row = connection.execute("SELECT id FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            raise ValueError(f"任务不存在：{task_id}")
        return int(row["id"])

    def _attempt_row_id(self, attempt_id: str) -> int | None:
        """读取尝试轮在数据库里的内部主键"""

        with connect_sqlite(self.database_path) as connection:
            row = connection.execute("SELECT id FROM attempts WHERE attempt_id = ?", (attempt_id,)).fetchone()
        if row is None:
            return None
        return int(row["id"])

    def create_attempt(self, record: AttemptRecord) -> AttemptRecord:
        """写入一条尝试轮记录"""

        return self.save_attempt(record)

    def save_attempt(self, record: AttemptRecord) -> AttemptRecord:
        """按 attempt_id 写入或更新一条尝试轮记录"""

        task_row_id = self._task_row_id(record.task_id)
        with connect_sqlite(self.database_path) as connection:
            # 这里先把所有可变字段整理成同一份 payload
            # insert 和 update 共用一套数据来源，避免两边字段慢慢漂移
            payload = (
                task_row_id,
                record.attempt_no,
                record.candidate_id,
                record.status,
                record.failure_type,
                record.build_exec_status,
                record.target_state,
                self._store_path(record.build_log_path),
                self._store_path(record.module_path),
                self._store_path(record.rewritten_patch_path),
                record.started_at.isoformat(),
                record.finished_at.isoformat() if record.finished_at else None,
                self._dump_model(record),
            )
            existing_row_id = self._attempt_row_id(record.attempt_id)
            if existing_row_id is None:
                # attempt_id 是业务主键
                # 第一次看到时插入，后面同一轮状态推进时只做覆盖更新
                connection.execute(
                    """
                    INSERT INTO attempts(
                        task_id, attempt_no, attempt_id, candidate_id, status, failure_type,
                        build_exec_status, target_state, build_log_path, module_path,
                        rewritten_patch_path, started_at, finished_at, summary_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task_row_id,
                        record.attempt_no,
                        record.attempt_id,
                        record.candidate_id,
                        record.status,
                        record.failure_type,
                        record.build_exec_status,
                        record.target_state,
                        self._store_path(record.build_log_path),
                        self._store_path(record.module_path),
                        self._store_path(record.rewritten_patch_path),
                        record.started_at.isoformat(),
                        record.finished_at.isoformat() if record.finished_at else None,
                        self._dump_model(record),
                    ),
                )
            else:
                # report、replay、Web 详情页都依赖 attempts 表读取当前轮最终状态
                # 所以同一 attempt_id 后续推进时必须原地更新，而不是重复插入
                connection.execute(
                    """
                    UPDATE attempts
                    SET task_id = ?,
                        attempt_no = ?,
                        candidate_id = ?,
                        status = ?,
                        failure_type = ?,
                        build_exec_status = ?,
                        target_state = ?,
                        build_log_path = ?,
                        module_path = ?,
                        rewritten_patch_path = ?,
                        started_at = ?,
                        finished_at = ?,
                        summary_json = ?
                    WHERE attempt_id = ?
                    """,
                    (*payload, record.attempt_id),
                )
            connection.commit()
        return record

    def save_attempt_state(self, state: AttemptState) -> AttemptState:
        """写入当前轮的主状态快照"""

        with connect_sqlite(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO attempt_states(task_ref, attempt_no, stage, remaining_budget_json, disabled_strategies_json, termination_reason, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state.task_id,
                    state.attempt_no,
                    state.stage,
                    json.dumps(state.remaining_budget, ensure_ascii=False),
                    json.dumps(state.disabled_strategies, ensure_ascii=False),
                    state.termination_reason,
                    self._dump_model(state),
                ),
            )
            connection.commit()
        return state

    def save_failure_record(self, record: FailureRecord) -> FailureRecord:
        """写入结构化失败归因"""

        with connect_sqlite(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO failure_records(task_ref, attempt_ref, stage_name, failure_type, summary, evidence_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.task_id,
                    record.attempt_id,
                    record.stage_name,
                    record.failure_type,
                    record.summary,
                    json.dumps(record.evidence, ensure_ascii=False),
                    record.created_at.isoformat(),
                ),
            )
            connection.commit()
        return record

    def save_validation_report(self, attempt_id: str, report: ValidationReport) -> ValidationReport:
        """写入加载、卸载和语义校验结果"""

        attempt_row_id = self._attempt_row_id(attempt_id)
        if attempt_row_id is None:
            raise ValueError(f"尝试轮不存在：{attempt_id}")

        validation_status = report.status

        with connect_sqlite(self.database_path) as connection:
            # 这里保留原始结果 JSON，而不是只存几个布尔值
            # 后面要做细粒度回放、前端详情页和人工复核时都能直接复用
            connection.execute(
                """
                INSERT INTO validation_records(
                    attempt_id, status, load_ok, unload_ok, smoke_ok, regression_ok, summary,
                    load_result_json, unload_result_json, smoke_result_json, semantic_guard_result_json,
                    semantic_precheck_result_json, selftest_result_json, regression_result_json, validation_matrix_json,
                    validation_intensity
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt_row_id,
                    validation_status,
                    int(report.load_result.ok),
                    int(report.unload_result.ok),
                    int(report.smoke_result.ok),
                    int(report.regression_result.ok),
                    "；".join(report.notes) if report.notes else "验证结果已记录",
                    report.load_result.model_dump_json(),
                    report.unload_result.model_dump_json(),
                    report.smoke_result.model_dump_json(),
                    report.semantic_guard_result.model_dump_json(),
                    report.semantic_precheck_result.model_dump_json(),
                    report.selftest_result.model_dump_json(),
                    report.regression_result.model_dump_json(),
                    json.dumps([item.model_dump(mode="json") for item in report.validation_matrix], ensure_ascii=False),
                    report.validation_intensity,
                ),
            )
            connection.commit()
        return report

    def save_harness_trace(self, trace: HarnessTrace, trace_path: Path | None = None) -> HarnessTrace:
        """写入单轮 harness trace 索引"""

        with connect_sqlite(self.database_path) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO harness_traces(trace_id, task_ref, attempt_ref, trace_path, summary_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    trace.trace_id,
                    trace.task_id,
                    f"{trace.task_id}-A{trace.attempt_no:03d}",
                    self._store_path(trace_path),
                    self._dump_model(trace),
                ),
            )
            connection.commit()
        return trace

    def save_evidence_spans(self, task_id: str, attempt_id: str | None, spans: list[EvidenceSpan]) -> list[EvidenceSpan]:
        """写入证据片段索引"""

        if not spans:
            return spans

        with connect_sqlite(self.database_path) as connection:
            connection.executemany(
                """
                INSERT INTO evidence_spans(task_ref, attempt_ref, evidence_id, source_type, source_path, excerpt, start_line, end_line, score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        task_id,
                        attempt_id,
                        span.evidence_id,
                        span.source_type,
                        to_project_relative(self.project_root, span.source_path),
                        span.excerpt,
                        span.start_line,
                        span.end_line,
                        span.score,
                    )
                    for span in spans
                ],
            )
            connection.commit()
        return spans

    def list_attempts(self, task_id: str) -> list[AttemptRecord]:
        """读取任务的所有尝试轮记录"""

        with connect_sqlite(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT attempts.attempt_id, attempts.attempt_no, attempts.candidate_id, attempts.status, attempts.failure_type,
                       attempts.build_exec_status, attempts.target_state, attempts.build_log_path,
                       attempts.module_path, attempts.rewritten_patch_path, attempts.started_at, attempts.finished_at,
                       tasks.task_id AS task_ref
                FROM attempts
                JOIN tasks ON attempts.task_id = tasks.id
                WHERE tasks.task_id = ?
                ORDER BY attempts.attempt_no ASC
                """,
                (task_id,),
            ).fetchall()

        records: list[AttemptRecord] = []
        for row in rows:
            # 查询层返回的是 sqlite 行对象
            # 这里统一恢复成 AttemptRecord，保证上层拿到的还是领域对象
            records.append(
                AttemptRecord(
                    task_id=row["task_ref"],
                    attempt_no=row["attempt_no"],
                    attempt_id=row["attempt_id"],
                    candidate_id=row["candidate_id"],
                    status=row["status"],
                    failure_type=row["failure_type"],
                    build_exec_status=row["build_exec_status"],
                    target_state=row["target_state"],
                    build_log_path=self._load_optional_path(row["build_log_path"]),
                    module_path=self._load_optional_path(row["module_path"]),
                    rewritten_patch_path=self._load_optional_path(row["rewritten_patch_path"]),
                    started_at=datetime.fromisoformat(row["started_at"]),
                    finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
                )
            )
        return records

    def next_attempt_no(self, task_id: str) -> int:
        """返回任务下一轮尝试的编号"""

        attempts = self.list_attempts(task_id)
        return len(attempts) + 1

    def latest_trace_summary(self, task_id: str) -> dict[str, object] | None:
        """读取任务最近一次 trace 的摘要"""

        with connect_sqlite(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT summary_json, trace_path
                FROM harness_traces
                WHERE task_ref = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (task_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "trace_path": row["trace_path"],
            "summary": json.loads(row["summary_json"]) if row["summary_json"] else {},
        }

    def _store_path(self, path: Path | None) -> str | None:
        """把项目内路径转换成相对源码根目录的表达"""

        return to_project_relative(self.project_root, path)

    def _load_optional_path(self, value: str | None) -> Path | None:
        """恢复数据库中的可选路径字段"""

        return resolve_project_path(self.project_root, value)

    def _dump_model(self, model: object) -> str:
        """把模型按项目路径策略序列化为 JSON"""

        return json.dumps(relativize_payload(model, self.project_root), ensure_ascii=False)
