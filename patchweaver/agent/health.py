"""Task-local Agent health assessment."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from patchweaver.models.task import TaskContext
from patchweaver.utils.path_policy import to_project_relative

AgentHealthStatus = str

RUNNING_TASK_STATUSES = {"created", "running", "analyzing", "building", "validating", "reporting"}
TERMINAL_TASK_STATUSES = {"built", "failed", "reported", "target_state", "completed", "succeeded"}
TERMINAL_FAILURE_TYPES = {"source_unavailable", "target_already_patched", "unsupported_livepatch", "unsupported_kpatch"}
STALE_AFTER_SECONDS = 60 * 60
LONG_BUILD_AFTER_SECONDS = 45 * 60


def evaluate_agent_health(
    *,
    task: TaskContext,
    attempts: Sequence[Any],
    project_root: Path | None = None,
    now: datetime | None = None,
    stale_after_seconds: int = STALE_AFTER_SECONDS,
    long_build_after_seconds: int = LONG_BUILD_AFTER_SECONDS,
    write: bool = True,
) -> dict[str, Any]:
    """Return a task health snapshot and optionally persist it under the task workspace."""

    current_time = _as_aware(now or datetime.now(timezone.utc))
    task_dir = task.workspace_dir.resolve()
    latest_attempt = attempts[-1] if attempts else None
    latest_failure = _latest_failure(task_dir, latest_attempt)
    latest_failure_type = _latest_failure_type(latest_attempt, latest_failure)
    trace_path = _select_agent_trace_path(task_dir)
    trace_payload = _load_json(trace_path)
    report_json_path = task_dir / "reports" / "report.json"
    report_md_path = task_dir / "reports" / "report.md"

    signals: list[str] = []
    evidence: list[dict[str, Any]] = []
    recommendations: list[str] = []

    if latest_failure_type in TERMINAL_FAILURE_TYPES:
        signals.append(latest_failure_type)
        recommendations.append("停止自动重试，保留终止原因并让页面展示为 terminal")
        if task.status in RUNNING_TASK_STATUSES:
            signals.append("terminal_but_retrying")
            recommendations.append("终止型失败仍处于运行态，请停止后续 attempt 消耗")
        status: AgentHealthStatus = "terminal"
    elif _is_retry_loop(task_dir, attempts):
        status = "retry_loop"
        signals.append("ineffective_retry_loop")
        recommendations.append("连续 attempt 的失败桶和改写形态没有变化，请切换 recipe 或转人工复核")
    elif _has_missing_evidence(
        task=task,
        task_dir=task_dir,
        latest_attempt=latest_attempt,
        trace_path=trace_path,
        report_json_path=report_json_path,
        report_md_path=report_md_path,
    ):
        status = "evidence_missing"
        if _has_agent_decision_fields(task_dir, latest_attempt) and not trace_path.exists():
            signals.append("missing_agent_trace")
            recommendations.append("补齐 agent_workflow_trace.json，避免只展示静态 running")
        if task.status in TERMINAL_TASK_STATUSES and (not report_json_path.exists() or not report_md_path.exists()):
            signals.append("missing_report_or_replay")
            recommendations.append("补齐 report.json/report.md 和 replay 证据后再视为闭环")
    elif _is_stale_running(
        task=task,
        task_dir=task_dir,
        attempts=attempts,
        now=current_time,
        stale_after_seconds=stale_after_seconds,
    ):
        status = "stale"
        signals.append("stale_running_task")
        recommendations.append("检查 Agent 进程、最新日志和 workflow trace 是否仍在推进")
        if _is_long_build_stage(task_dir, latest_attempt, current_time, long_build_after_seconds):
            signals.append("long_build_stage")
            recommendations.append("构建阶段超过阈值，请查看进程、build.log 和 timeout")
    elif task.status in TERMINAL_TASK_STATUSES or trace_path.exists() or attempts:
        status = "healthy"
        signals.append("progress_observed")
    else:
        status = "unknown"
        signals.append("insufficient_evidence")

    for path in _health_evidence_paths(task_dir, latest_attempt):
        evidence.append(
            {
                "path": to_project_relative(project_root, path),
                "exists": path.exists(),
                "mtime": _mtime_iso(path),
            }
        )

    payload = {
        "task_id": task.task_id,
        "status": status,
        "signals": signals,
        "recommendations": _dedupe(recommendations),
        "latest_failure_type": latest_failure_type,
        "latest_attempt_no": latest_attempt.attempt_no if latest_attempt is not None else None,
        "latest_trace_decision_count": _decision_count(trace_payload),
        "checked_at": current_time.isoformat(),
        "evidence": evidence,
        "source_paths": {
            "agent_workflow_trace": to_project_relative(project_root, trace_path),
            "agent_auto_workflow_trace": to_project_relative(project_root, task_dir / "agent" / "agent_auto_workflow_trace.json"),
            "report_json": to_project_relative(project_root, report_json_path),
            "report_md": to_project_relative(project_root, report_md_path),
            "agent_health": to_project_relative(project_root, task_dir / "agent" / "agent_health.json"),
        },
    }

    if write:
        health_path = task_dir / "agent" / "agent_health.json"
        health_path.parent.mkdir(parents=True, exist_ok=True)
        health_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return payload


def _latest_failure(task_dir: Path, latest_attempt: Any | None) -> dict[str, Any] | None:
    if latest_attempt is not None:
        return _load_json(task_dir / "attempts" / f"{latest_attempt.attempt_no:03d}" / "logs" / "failure_record.json")
    return _load_json(task_dir / "analysis" / "trace" / "failure_record.json")


def _latest_failure_type(latest_attempt: Any | None, latest_failure: dict[str, Any] | None) -> str | None:
    if latest_attempt is not None and getattr(latest_attempt, "failure_type", None):
        return str(latest_attempt.failure_type)
    value = (latest_failure or {}).get("failure_type")
    return str(value) if value else None


def _has_missing_evidence(
    *,
    task: TaskContext,
    task_dir: Path,
    latest_attempt: Any | None,
    trace_path: Path,
    report_json_path: Path,
    report_md_path: Path,
) -> bool:
    if _has_agent_decision_fields(task_dir, latest_attempt) and not trace_path.exists():
        return True
    if task.status in TERMINAL_TASK_STATUSES and (not report_json_path.exists() or not report_md_path.exists()):
        return True
    if task.status in {"built", "reported", "completed", "succeeded"} and latest_attempt is not None:
        attempt_dir = task_dir / "attempts" / f"{latest_attempt.attempt_no:03d}"
        return not (attempt_dir / "trace" / "harness_trace.json").exists()
    return False


def _has_agent_decision_fields(task_dir: Path, latest_attempt: Any | None) -> bool:
    if (task_dir / "analysis" / "repair_intent.json").exists():
        return True
    if latest_attempt is None:
        return False
    attempt_dir = task_dir / "attempts" / f"{latest_attempt.attempt_no:03d}"
    if (attempt_dir / "rewrite" / "rewrite_plan.json").exists():
        return True
    failure = _load_json(attempt_dir / "logs" / "failure_record.json")
    return bool(failure and (failure.get("agent_next_action") or failure.get("diagnostic_details")))


def _is_stale_running(
    *,
    task: TaskContext,
    task_dir: Path,
    attempts: Sequence[Any],
    now: datetime,
    stale_after_seconds: int,
) -> bool:
    if task.status not in RUNNING_TASK_STATUSES:
        return False
    newest = max([_as_aware(task.updated_at), *(_path_mtimes(task_dir)), *(_attempt_datetimes(attempts))], default=_as_aware(task.updated_at))
    return (now - newest).total_seconds() >= stale_after_seconds


def _is_long_build_stage(task_dir: Path, latest_attempt: Any | None, now: datetime, long_build_after_seconds: int) -> bool:
    if latest_attempt is None or getattr(latest_attempt, "status", None) not in {"running", "building", "created"}:
        return False
    attempt_dir = task_dir / "attempts" / f"{latest_attempt.attempt_no:03d}"
    build_log = attempt_dir / "logs" / "build.log"
    marker = _mtime(build_log) or _as_aware(getattr(latest_attempt, "started_at", now))
    return (now - marker).total_seconds() >= long_build_after_seconds


def _is_retry_loop(task_dir: Path, attempts: Sequence[Any]) -> bool:
    if len(attempts) < 2:
        return False
    signatures = [_attempt_signature(task_dir, attempt) for attempt in attempts[-3:]]
    comparable = [signature for signature in signatures if signature["failure_bucket"] or signature["rewrite_shape"] or signature["patch_hash"]]
    if len(comparable) < 2:
        return False
    first = comparable[0]
    return all(item == first for item in comparable[1:])


def _attempt_signature(task_dir: Path, attempt: Any) -> dict[str, str | None]:
    attempt_dir = task_dir / "attempts" / f"{attempt.attempt_no:03d}"
    failure = _load_json(attempt_dir / "logs" / "failure_record.json") or {}
    rewrite_plan = _load_json(attempt_dir / "rewrite" / "rewrite_plan.json") or {}
    patch_path = attempt_dir / "rewrite" / "rewritten.patch"
    failure_type = getattr(attempt, "failure_type", None) or failure.get("failure_type")
    failure_bucket = "|".join(
        str(part)
        for part in [
            failure_type,
            failure.get("stage_name"),
            failure.get("summary"),
        ]
        if part
    )
    rewrite_shape = "|".join(
        str(part)
        for part in [
            rewrite_plan.get("selected_recipe") or rewrite_plan.get("recipe"),
            rewrite_plan.get("selected_strategy") or rewrite_plan.get("strategy"),
        ]
        if part
    )
    return {
        "failure_bucket": failure_bucket or None,
        "rewrite_shape": rewrite_shape or None,
        "patch_hash": _sha256_file(patch_path),
    }


def _health_evidence_paths(task_dir: Path, latest_attempt: Any | None) -> list[Path]:
    paths = [
        task_dir / "agent" / "agent_workflow_trace.json",
        task_dir / "agent" / "agent_auto_workflow_trace.json",
        task_dir / "agent" / "auto_workflow_trace.json",
        task_dir / "agent" / "agent_health.json",
        task_dir / "reports" / "report.json",
        task_dir / "reports" / "report.md",
    ]
    if latest_attempt is not None:
        attempt_dir = task_dir / "attempts" / f"{latest_attempt.attempt_no:03d}"
        paths.extend(
            [
                attempt_dir / "logs" / "failure_record.json",
                attempt_dir / "logs" / "build.log",
                attempt_dir / "trace" / "harness_trace.json",
            ]
        )
    else:
        paths.append(task_dir / "analysis" / "trace" / "failure_record.json")
    return paths


def _path_mtimes(task_dir: Path) -> list[datetime]:
    if not task_dir.exists():
        return []
    return [_as_aware(datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)) for path in _safe_files(task_dir)]


def _safe_files(task_dir: Path) -> Iterable[Path]:
    for path in task_dir.rglob("*"):
        if path.is_file():
            yield path


def _attempt_datetimes(attempts: Sequence[Any]) -> list[datetime]:
    values: list[datetime] = []
    for attempt in attempts:
        for attr in ("started_at", "finished_at"):
            value = getattr(attempt, attr, None)
            if value is not None:
                values.append(_as_aware(value))
    return values


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _decision_count(payload: dict[str, Any] | None) -> int:
    payload = payload or {}
    decisions = payload.get("decisions")
    if isinstance(decisions, list):
        return len(decisions)
    plans = payload.get("plans")
    if isinstance(plans, list):
        return len(plans)
    nodes = payload.get("nodes")
    if isinstance(nodes, list):
        return sum(1 for item in nodes if isinstance(item, dict) and item.get("node") == "plan")
    return 0


def _select_agent_trace_path(task_dir: Path) -> Path:
    candidates = [
        task_dir / "agent" / "agent_workflow_trace.json",
        task_dir / "agent" / "agent_auto_workflow_trace.json",
        task_dir / "agent" / "auto_workflow_trace.json",
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mtime(path: Path) -> datetime | None:
    if not path.exists():
        return None
    return _as_aware(datetime.fromtimestamp(path.stat().st_mtime, timezone.utc))


def _mtime_iso(path: Path) -> str | None:
    value = _mtime(path)
    return value.isoformat() if value is not None else None


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
