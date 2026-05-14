from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from patchweaver.api.app import create_app
from patchweaver.api.deps import get_api_context


class _FakeTaskRepo:
    def __init__(self, task=None) -> None:
        self.task = task

    def get_task(self, task_id: str):
        return self.task if self.task is not None and self.task.task_id == task_id else None


class _FakeAttemptRepo:
    def __init__(self, attempts=None) -> None:
        self.attempts = attempts or []

    def list_attempts(self, task_id: str):
        return list(self.attempts)


@pytest.fixture
def workspace_tmp(request) -> Path:
    root = Path("data/cache/pytest-chat") / f"{request.node.name}-{uuid4().hex[:8]}"
    root.mkdir(parents=True, exist_ok=True)
    try:
        yield root.resolve()
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _context(project_root: Path, *, task=None, attempts=None) -> SimpleNamespace:
    workspace_root = project_root / "workspaces"
    workspace_root.mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(
        project_root=project_root,
        runtime=SimpleNamespace(workspace_root=workspace_root, data_dir=project_root / "data"),
        models_config=None,
        task_repo=_FakeTaskRepo(task),
        attempt_repo=_FakeAttemptRepo(attempts),
        artifact_repo=SimpleNamespace(list_artifacts=lambda task_id: []),
        logging_config=SimpleNamespace(
            file_path="data/logs/patchweaver.log",
            jsonl_path="data/logs/patchweaver.jsonl",
            enable_jsonl=True,
        ),
    )


def test_chat_endpoint_answers_overview_with_tool_trace(monkeypatch, workspace_tmp: Path) -> None:
    from patchweaver.agent import chat_tools

    class _OverviewService:
        def __init__(self, context) -> None:
            self.context = context

        def get_overview(self):
            return {
                "metrics": {"total_tasks": 2, "running_tasks": 1, "success_rate": 50},
                "recent_tasks": [
                    {"task_id": "TASK-001", "cve_id": "CVE-2024-26742", "status": "built"},
                    {"task_id": "TASK-002", "cve_id": "CVE-2024-26675", "status": "failed"},
                ],
                "failure_distribution": [{"failure_type": "kpatch_constraint", "total": 1}],
            }

    monkeypatch.setattr(chat_tools, "OverviewService", _OverviewService)
    context = _context(workspace_tmp)
    app = create_app()
    app.dependency_overrides[get_api_context] = lambda: context
    try:
        response = TestClient(app).post("/api/v1/chat", json={"message": "系统现在能做什么"})
    finally:
        app.dependency_overrides.clear()

    payload = response.json()
    assert response.status_code == 200
    assert payload["answer"]
    assert payload["session_id"]
    assert payload["tool_calls"][0]["name"] == "get_overview"
    assert payload["tool_calls"][0]["status"] == "success"


def test_get_task_detail_returns_latest_three_attempts(workspace_tmp: Path) -> None:
    from patchweaver.agent.chat_tools import get_task_detail

    task = SimpleNamespace(
        task_id="TASK-001",
        cve_id="CVE-2024-26742",
        target_kernel="6.6.102-5.2.an23.x86_64",
        status="failed",
        current_attempt=4,
        max_attempts=5,
        workspace_dir=workspace_tmp / "workspaces" / "TASK-001",
        updated_at=datetime(2026, 5, 14, 10, 0, 0),
    )
    attempts = [
        SimpleNamespace(attempt_no=1, attempt_id="A1", status="failed", failure_type="compile_failed"),
        SimpleNamespace(attempt_no=2, attempt_id="A2", status="failed", failure_type="patch_apply_failed"),
        SimpleNamespace(attempt_no=3, attempt_id="A3", status="failed", failure_type="kpatch_constraint"),
        SimpleNamespace(attempt_no=4, attempt_id="A4", status="built", failure_type=None),
    ]

    payload = get_task_detail("TASK-001", _context(workspace_tmp, task=task, attempts=attempts))

    assert payload["task"]["task_id"] == "TASK-001"
    assert [item["attempt_no"] for item in payload["latest_attempts"]] == [4, 3, 2]


def test_get_artifact_content_rejects_path_traversal(workspace_tmp: Path) -> None:
    from patchweaver.agent.chat_tools import get_artifact_content

    with pytest.raises(ValueError, match="非法产物路径"):
        get_artifact_content("../../config/models.yaml", _context(workspace_tmp))


def test_chat_endpoint_reads_doctor_report(monkeypatch, workspace_tmp: Path) -> None:
    from patchweaver.agent import chat_tools

    class _DoctorService:
        def __init__(self, context) -> None:
            self.context = context

        def get_report(self, *, refresh: bool = False):
            return {
                "summary": {"total": 2, "ok": 1, "warn": 0, "error": 1},
                "checks": [{"category": "model_backend", "name": "bailian_chat", "status": "error"}],
            }

    monkeypatch.setattr(chat_tools, "DoctorApiService", _DoctorService)
    app = create_app()
    app.dependency_overrides[get_api_context] = lambda: _context(workspace_tmp)
    try:
        response = TestClient(app).post("/api/v1/chat", json={"message": "环境诊断有什么问题"})
    finally:
        app.dependency_overrides.clear()

    payload = response.json()
    assert response.status_code == 200
    assert payload["tool_calls"][0]["name"] == "get_doctor_report"
    assert any("doctor_latest.json" in ref for ref in payload["evidence_refs"])


def test_chat_endpoint_explains_task_failure(monkeypatch, workspace_tmp: Path) -> None:
    from patchweaver.agent import chat_tools

    class _FailureExplanationService:
        def __init__(self, *, models_config=None) -> None:
            self.models_config = models_config

        def explain(self, *, failure_type, summary=None):
            return {"failure_type": failure_type, "explanation": "热补丁约束受限", "source": "fallback_rule"}

    monkeypatch.setattr(chat_tools, "FailureExplanationService", _FailureExplanationService)
    task = SimpleNamespace(
        task_id="TASK-001",
        cve_id="CVE-2024-26742",
        target_kernel="6.6.102-5.2.an23.x86_64",
        status="failed",
        current_attempt=1,
        max_attempts=3,
        workspace_dir=workspace_tmp / "workspaces" / "TASK-001",
        updated_at=datetime(2026, 5, 14, 10, 0, 0),
    )
    attempts = [SimpleNamespace(attempt_no=1, attempt_id="A1", status="failed", failure_type="kpatch_constraint")]
    app = create_app()
    app.dependency_overrides[get_api_context] = lambda: _context(workspace_tmp, task=task, attempts=attempts)
    try:
        response = TestClient(app).post(
            "/api/v1/chat",
            json={"message": "TASK-001为什么失败", "context": {"task_id": "TASK-001"}},
        )
    finally:
        app.dependency_overrides.clear()

    payload = response.json()
    assert response.status_code == 200
    assert [item["name"] for item in payload["tool_calls"]] == ["get_task_detail", "explain_failure"]
    assert "热补丁约束受限" in payload["answer"]


def test_get_artifact_content_reads_workspace_text(workspace_tmp: Path) -> None:
    from patchweaver.agent.chat_tools import get_artifact_content

    target = workspace_tmp / "workspaces" / "TASK-001" / "reports" / "report.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# report\nok\n", encoding="utf-8")

    payload = get_artifact_content("workspaces/TASK-001/reports/report.md", _context(workspace_tmp))

    assert payload["path"] == "workspaces/TASK-001/reports/report.md"
    assert payload["content"].startswith("# report")


def test_get_task_report_returns_report_summary(workspace_tmp: Path) -> None:
    from patchweaver.agent.chat_tools import get_task_report

    task = SimpleNamespace(
        task_id="TASK-001",
        cve_id="CVE-2024-26742",
        target_kernel="6.6.102-5.2.an23.x86_64",
        status="reported",
        current_attempt=1,
        max_attempts=3,
        workspace_dir=workspace_tmp / "workspaces" / "TASK-001",
    )
    report_path = task.workspace_dir / "reports" / "report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text('{"status":"failed","selected_recipe":"section_avoidance"}\n', encoding="utf-8")

    payload = get_task_report("TASK-001", _context(workspace_tmp, task=task))

    assert payload["report_path"] == "workspaces/TASK-001/reports/report.json"
    assert payload["summary"]["selected_recipe"] == "section_avoidance"


def test_search_docs_rag_returns_top_three(monkeypatch, workspace_tmp: Path) -> None:
    from patchweaver.agent import chat_tools

    class _RagApiService:
        def __init__(self, context) -> None:
            self.context = context

        def search(self, *, query, limit=None, cve_id=None, subsystem=None):
            return {
                "items": [
                    {"text": "A", "card_path": "docs/a.md"},
                    {"text": "B", "card_path": "docs/b.md"},
                    {"text": "C", "card_path": "docs/c.md"},
                    {"text": "D", "card_path": "docs/d.md"},
                ]
            }

    monkeypatch.setattr(chat_tools, "RagApiService", _RagApiService)

    payload = chat_tools.search_docs_rag("怎么使用", _context(workspace_tmp))

    assert [item["source"] for item in payload["results"]] == ["docs/a.md", "docs/b.md", "docs/c.md"]


def test_suggested_start_auto_run_requires_confirmation() -> None:
    from patchweaver.agent.chat_tools import suggest_start_auto_run

    action = suggest_start_auto_run("TASK-001")

    assert action.type == "start_auto_run"
    assert action.requires_confirmation is True
    assert action.payload == {"task_id": "TASK-001"}


def test_chat_endpoint_returns_confirmed_start_auto_run_action(workspace_tmp: Path) -> None:
    task = SimpleNamespace(
        task_id="TASK-001",
        cve_id="CVE-2024-26742",
        target_kernel="6.6.102-5.2.an23.x86_64",
        status="analyzed",
        current_attempt=0,
        max_attempts=3,
        workspace_dir=workspace_tmp / "workspaces" / "TASK-001",
    )
    app = create_app()
    app.dependency_overrides[get_api_context] = lambda: _context(workspace_tmp, task=task, attempts=[])
    try:
        response = TestClient(app).post(
            "/api/v1/chat",
            json={"message": "TASK-001继续自动运行", "context": {"task_id": "TASK-001"}},
        )
    finally:
        app.dependency_overrides.clear()

    payload = response.json()
    assert response.status_code == 200
    assert payload["requires_confirmation"] is True
    assert payload["suggested_actions"][0]["type"] == "start_auto_run"
    assert payload["suggested_actions"][0]["requires_confirmation"] is True
