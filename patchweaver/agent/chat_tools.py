"""Read-only tools exposed to the Web Chat Assistant."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from patchweaver.api.deps import ApiContext
from patchweaver.api.schemas.chat import SuggestedAction
from patchweaver.api.services.artifact_service import ArtifactService
from patchweaver.api.services.doctor_service import DoctorApiService
from patchweaver.api.services.failure_explanation_service import FailureExplanationService
from patchweaver.api.services.overview_service import OverviewService
from patchweaver.api.services.rag_service import RagApiService
from patchweaver.utils.path_policy import to_project_relative

_ALLOWED_ARTIFACT_SUFFIXES = {".json", ".md", ".log"}


def get_overview(context: ApiContext) -> dict[str, Any]:
    """Return a compact overview snapshot for chat answers."""

    payload = OverviewService(context).get_overview()
    recent_tasks = payload.get("recent_tasks") if isinstance(payload, dict) else []
    return {
        "metrics": payload.get("metrics", {}) if isinstance(payload, dict) else {},
        "recent_tasks": recent_tasks[:5] if isinstance(recent_tasks, list) else [],
        "failure_distribution": payload.get("failure_distribution", []) if isinstance(payload, dict) else [],
        "evidence_refs": ["data/patchweaver.db"],
    }


def get_task_detail(task_id: str, context: ApiContext) -> dict[str, Any]:
    """Return task metadata plus the latest three attempts."""

    task = context.task_repo.get_task(task_id)
    if task is None:
        raise ValueError(f"未找到任务 {task_id}")
    attempts = context.attempt_repo.list_attempts(task_id)
    latest_attempts = sorted(attempts, key=lambda item: int(getattr(item, "attempt_no", 0) or 0), reverse=True)[:3]
    workspace_dir = Path(getattr(task, "workspace_dir", context.project_root / "workspaces" / task_id))
    evidence_refs = [to_project_relative(context.project_root, workspace_dir / "task_context.json")]
    latest_attempt_no = getattr(latest_attempts[0], "attempt_no", None) if latest_attempts else None
    if latest_attempt_no is not None:
        evidence_refs.append(to_project_relative(context.project_root, workspace_dir / "attempts" / f"{int(latest_attempt_no):03d}" / "logs" / "failure_record.json"))
    return {
        "task": _task_payload(task, context.project_root),
        "latest_attempts": [_attempt_payload(item) for item in latest_attempts],
        "evidence_refs": [str(item) for item in evidence_refs],
    }


def explain_failure(failure_type: str, summary: str, context: ApiContext) -> dict[str, Any]:
    """Explain a failure type with the existing short explanation service."""

    return FailureExplanationService(models_config=getattr(context, "models_config", None)).explain(
        failure_type=failure_type,
        summary=summary,
    )


def get_doctor_report(context: ApiContext) -> dict[str, Any]:
    """Return a compact doctor report."""

    payload = DoctorApiService(context).get_report(refresh=False)
    checks = payload.get("checks") if isinstance(payload, dict) else []
    report_path = context.runtime.data_dir / "traces" / "doctor_latest.json"
    summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
    status = "error" if isinstance(summary, dict) and int(summary.get("error", 0) or 0) > 0 else "ok"
    return {
        "status": status,
        "summary": summary,
        "checks": checks[:12] if isinstance(checks, list) else [],
        "report_path": str(to_project_relative(context.project_root, report_path)),
        "evidence_refs": [str(to_project_relative(context.project_root, report_path))],
    }


def get_task_report(task_id: str, context: ApiContext) -> dict[str, Any]:
    """Return a compact task report summary."""

    tree = ArtifactService(context).list_tree(task_id)
    report_path = ((tree.get("key_artifacts") or {}).get("report_json") if isinstance(tree, dict) else None) or f"workspaces/{task_id}/reports/report.json"
    project_path = context.project_root / str(report_path)
    if not project_path.exists():
        raise FileNotFoundError(f"未找到任务报告 {task_id}")
    payload = _read_json(project_path)
    return {
        "task_id": task_id,
        "report_path": report_path,
        "summary": _report_summary(payload),
        "evidence_refs": [report_path],
    }


def get_artifact_content(path: str, context: ApiContext) -> dict[str, Any]:
    """Read a safe workspace artifact and return a clipped text preview."""

    normalized = str(path or "").replace("\\", "/").lstrip("/")
    if not normalized or ".." in Path(normalized).parts:
        raise ValueError(f"非法产物路径：{path}")
    if not normalized.startswith("workspaces/"):
        raise ValueError(f"非法产物路径：{path}")
    candidate = (context.project_root / normalized).resolve()
    workspace_root = Path(getattr(context.runtime, "workspace_root", context.project_root / "workspaces")).resolve()
    if workspace_root != candidate and workspace_root not in candidate.parents:
        raise ValueError(f"非法产物路径：{path}")
    if candidate.suffix.lower() not in _ALLOWED_ARTIFACT_SUFFIXES:
        raise ValueError(f"不支持的产物类型：{candidate.suffix}")
    if not candidate.exists() or not candidate.is_file():
        raise FileNotFoundError(f"找不到产物文件：{path}")
    content = candidate.read_text(encoding="utf-8", errors="replace")
    truncated = len(content) > 3000
    return {
        "path": str(to_project_relative(context.project_root, candidate)),
        "content": content[:3000],
        "truncated": truncated,
        "evidence_refs": [str(to_project_relative(context.project_root, candidate))],
    }


def search_docs_rag(query: str, context: ApiContext) -> dict[str, Any]:
    """Search PatchWeaver docs through the existing RAG service."""

    payload = RagApiService(context).search(query=query, limit=3)
    items = payload.get("items") if isinstance(payload, dict) else []
    return {
        "results": [
            {
                "text": str(item.get("text") or "")[:800],
                "source": item.get("card_path") or item.get("chunk_id") or "",
            }
            for item in items[:3]
            if isinstance(item, dict)
        ],
        "evidence_refs": [
            str(item.get("card_path") or item.get("chunk_id"))
            for item in items[:3]
            if isinstance(item, dict) and (item.get("card_path") or item.get("chunk_id"))
        ],
    }


def suggest_create_task(cve_id: str, kernel: str) -> SuggestedAction:
    return SuggestedAction(
        type="create_task",
        label=f"创建任务 {cve_id}",
        payload={"cve_id": cve_id, "kernel": kernel},
        requires_confirmation=True,
    )


def suggest_start_auto_run(task_id: str) -> SuggestedAction:
    return SuggestedAction(
        type="start_auto_run",
        label=f"启动自动运行 {task_id}",
        payload={"task_id": task_id},
        requires_confirmation=True,
    )


def suggest_run_doctor_repair() -> SuggestedAction:
    return SuggestedAction(
        type="run_doctor_repair",
        label="执行环境修复",
        payload={},
        requires_confirmation=True,
    )


def _task_payload(task: Any, project_root: Path) -> dict[str, Any]:
    return {
        "task_id": getattr(task, "task_id", None),
        "cve_id": getattr(task, "cve_id", None),
        "target_kernel": getattr(task, "target_kernel", None),
        "status": getattr(task, "status", None),
        "current_attempt": getattr(task, "current_attempt", None),
        "max_attempts": getattr(task, "max_attempts", None),
        "workspace_dir": str(to_project_relative(project_root, Path(getattr(task, "workspace_dir")))) if getattr(task, "workspace_dir", None) else None,
        "updated_at": _json_value(getattr(task, "updated_at", None)),
    }


def _attempt_payload(attempt: Any) -> dict[str, Any]:
    return {
        "attempt_no": getattr(attempt, "attempt_no", None),
        "attempt_id": getattr(attempt, "attempt_id", None),
        "status": getattr(attempt, "status", None),
        "failure_type": getattr(attempt, "failure_type", None),
        "build_exec_status": getattr(attempt, "build_exec_status", None),
        "target_state": getattr(attempt, "target_state", None),
        "updated_at": _json_value(getattr(attempt, "updated_at", None)),
    }


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _report_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": payload.get("status") or payload.get("final_status"),
        "task_id": payload.get("task_id"),
        "cve_id": payload.get("cve_id"),
        "selected_recipe": payload.get("selected_recipe"),
        "failure_type": payload.get("failure_type"),
    }
