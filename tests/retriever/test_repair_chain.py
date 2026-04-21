from __future__ import annotations

import json
from types import SimpleNamespace
from pathlib import Path

from patchweaver.models.task import TaskContext
from patchweaver.retriever.repair_chain import RepairChainResolver
from patchweaver.retriever.service import RetrieverService


def test_fetch_nvd_record_falls_back_when_source_unavailable(monkeypatch) -> None:
    resolver = RepairChainResolver()

    def fake_fetch_json(url: str, *, source_name: str, stage: str) -> dict[str, object]:
        raise ValueError(f"请求来源失败：{url} (503)")

    monkeypatch.setattr(resolver, "_fetch_json", fake_fetch_json)

    record = resolver._fetch_nvd_record("CVE-2024-1086")

    assert record["references"] == []
    assert "503" in str(record["_fetch_error"])


def test_fetch_text_retries_after_timeout(monkeypatch) -> None:
    resolver = RepairChainResolver()
    resolver._start_fetch_trace("CVE-TEST-0001")
    calls = {"count": 0}

    class DummyResponse:
        """模拟一个最小可读的 HTTP 响应"""

        def __init__(self, body: bytes) -> None:
            self.headers = SimpleNamespace(get_content_charset=lambda: "utf-8")
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def read(self) -> bytes:
            return self.body

    def fake_urlopen(request, timeout: int):  # noqa: ANN001
        calls["count"] += 1
        if calls["count"] < 3:
            raise TimeoutError("The read operation timed out")
        return DummyResponse(b"ok")

    monkeypatch.setattr("patchweaver.retriever.repair_chain.urlopen", fake_urlopen)
    monkeypatch.setattr("patchweaver.retriever.repair_chain.time.sleep", lambda seconds: None)

    payload = resolver._fetch_text("https://example.com/demo.patch", source_name="demo", stage="patch")

    assert payload == "ok"
    assert calls["count"] == 3
    trace = resolver.latest_fetch_trace()
    assert trace is not None
    assert trace["summary"]["request_count"] == 3
    assert trace["summary"]["success_count"] == 1
    assert trace["summary"]["failure_count"] == 2


def test_fetch_patch_text_falls_back_to_next_candidate(monkeypatch) -> None:
    resolver = RepairChainResolver()

    def fake_fetch_text(url: str, *, source_name: str, stage: str) -> str:
        if "kernel.org" in url:
            raise ValueError("请求来源失败：kernel.org (The read operation timed out)")
        return "patch-body"

    monkeypatch.setattr(resolver, "_fetch_text", fake_fetch_text)
    selected_ref = {
        "source_name": "linux-stable",
        "commit_id": "1234567",
        "patch_urls": [
            "https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/patch/?id=1234567",
            "https://github.com/gregkh/linux/commit/1234567.patch",
        ],
    }

    payload = resolver._fetch_patch_text(selected_ref)

    assert payload == "patch-body"
    assert selected_ref["selected_patch_url"] == "https://github.com/gregkh/linux/commit/1234567.patch"


def test_retriever_service_writes_source_fetch_trace(monkeypatch, tmp_path: Path) -> None:
    service = RetrieverService()
    task = TaskContext(
        task_id="TASK-RETRIEVER-001",
        cve_id="CVE-2024-1086",
        target_kernel="6.6.102-5.2.an23.x86_64",
        workspace_dir=tmp_path / "workspaces" / "TASK-RETRIEVER-001",
    )
    raw_patch_path = task.workspace_dir / "input" / "raw_patch.patch"

    monkeypatch.setattr(
        service.repair_chain,
        "resolve",
        lambda cve_id: {
            "upstream_commit": "abcdef1",
            "stable_commit": "1234567",
            "commit_message": "demo patch",
            "raw_patch_text": "diff --git a/demo.c b/demo.c\n",
            "affected_files": ["demo.c"],
            "source_evidence": [],
            "fetch_trace": {
                "cve_id": cve_id,
                "status": "passed",
                "events": [],
                "summary": {"request_count": 1, "success_count": 1, "failure_count": 0},
            },
        },
    )

    bundle = service.fetch_patch_bundle(task=task, raw_patch_path=raw_patch_path)

    trace_path = task.workspace_dir / "analysis" / "trace" / "source_fetch_trace.json"
    assert bundle.stable_commit == "1234567"
    assert trace_path.exists()
    trace_payload = json.loads(trace_path.read_text(encoding="utf-8"))
    assert trace_payload["status"] == "passed"
