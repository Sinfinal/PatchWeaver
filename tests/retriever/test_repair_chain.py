from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

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


def test_fetch_text_uses_fresh_cache_before_network(monkeypatch, tmp_path: Path) -> None:
    resolver = RepairChainResolver(cache_dir=tmp_path / "cache")
    resolver._start_fetch_trace("CVE-TEST-0002")
    resolver._write_cache(
        "https://example.com/from-cache.patch",
        source_name="demo",
        stage="patch",
        content="cached-body",
    )

    def fail_urlopen(request, timeout: int):  # noqa: ANN001
        raise AssertionError("fresh cache 命中后不应该再发网络请求")

    monkeypatch.setattr("patchweaver.retriever.repair_chain.urlopen", fail_urlopen)

    payload = resolver._fetch_text("https://example.com/from-cache.patch", source_name="demo", stage="patch")

    assert payload == "cached-body"
    trace = resolver.latest_fetch_trace()
    assert trace is not None
    assert trace["summary"]["cache_hit_count"] == 1
    assert trace["events"][-1]["outcome"] == "cache_hit"


def test_fetch_text_uses_stale_cache_after_network_failure(monkeypatch, tmp_path: Path) -> None:
    resolver = RepairChainResolver(cache_dir=tmp_path / "cache")
    resolver.cache_ttl_sec = 0
    resolver.stale_cache_ttl_sec = 3600
    resolver._start_fetch_trace("CVE-TEST-0003")
    resolver._write_cache(
        "https://example.com/stale.patch",
        source_name="demo",
        stage="patch",
        content="stale-body",
    )
    cache_meta_path = next((tmp_path / "cache").glob("*.json"))
    cache_meta = json.loads(cache_meta_path.read_text(encoding="utf-8"))
    cache_meta["stored_at"] = cache_meta["stored_at"] - 60
    cache_meta_path.write_text(json.dumps(cache_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def fake_urlopen(request, timeout: int):  # noqa: ANN001
        raise TimeoutError("The read operation timed out")

    monkeypatch.setattr("patchweaver.retriever.repair_chain.urlopen", fake_urlopen)
    monkeypatch.setattr("patchweaver.retriever.repair_chain.time.sleep", lambda seconds: None)

    payload = resolver._fetch_text("https://example.com/stale.patch", source_name="demo", stage="patch")

    assert payload == "stale-body"
    trace = resolver.latest_fetch_trace()
    assert trace is not None
    assert trace["summary"]["failure_count"] == 3
    assert trace["summary"]["stale_cache_hit_count"] == 1
    assert trace["events"][-1]["outcome"] == "stale_cache_fallback"


def test_fetch_text_shares_cache_across_candidate_urls(monkeypatch, tmp_path: Path) -> None:
    resolver = RepairChainResolver(cache_dir=tmp_path / "cache")
    resolver._start_fetch_trace("CVE-TEST-0004")
    calls: list[str] = []

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
        calls.append(request.full_url)
        return DummyResponse(b"shared-body")

    monkeypatch.setattr("patchweaver.retriever.repair_chain.urlopen", fake_urlopen)

    first = resolver._fetch_text(
        "https://cdn.jsdelivr.net/demo.json",
        source_name="cvelistV5",
        stage="metadata",
        cache_key="cvelistV5:CVE-TEST-0004",
    )
    second = resolver._fetch_text(
        "https://raw.githubusercontent.com/demo.json",
        source_name="cvelistV5",
        stage="metadata",
        cache_key="cvelistV5:CVE-TEST-0004",
    )

    assert first == "shared-body"
    assert second == "shared-body"
    assert calls == ["https://cdn.jsdelivr.net/demo.json"]
    trace = resolver.latest_fetch_trace()
    assert trace is not None
    assert trace["summary"]["success_count"] == 1
    assert trace["summary"]["cache_hit_count"] == 1


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


def test_derive_stable_probe_refs_from_upstream_commit() -> None:
    resolver = RepairChainResolver()

    stable_refs = resolver._derive_stable_probe_refs(
        stable_refs=[],
        upstream_refs=[
            {
                "source_name": "upstream",
                "commit_id": "722d94847de29310e8aa03fcbdb41fc92c521756",
                "url": "https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=722d94847de29310e8aa03fcbdb41fc92c521756",
            }
        ],
    )

    assert stable_refs == [
        {
            "url": "https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/commit/?id=722d94847de29310e8aa03fcbdb41fc92c521756",
            "source_name": "linux-stable",
            "commit_id": "722d94847de29310e8aa03fcbdb41fc92c521756",
            "patch_url": "https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/patch/?id=722d94847de29310e8aa03fcbdb41fc92c521756",
            "patch_urls": [
                "https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/patch/?id=722d94847de29310e8aa03fcbdb41fc92c521756",
                "https://github.com/gregkh/linux/commit/722d94847de29310e8aa03fcbdb41fc92c521756.patch",
            ],
        }
    ]


def test_fetch_patch_reference_falls_back_from_stable_to_upstream(monkeypatch) -> None:
    resolver = RepairChainResolver()

    def fake_fetch_patch_text(selected_ref: dict[str, str | None]) -> str:
        if selected_ref["source_name"] == "linux-stable":
            raise ValueError("stable 来源不可用")
        selected_ref["selected_patch_url"] = "https://github.com/torvalds/linux/commit/abcdef1.patch"
        return "patch-body"

    monkeypatch.setattr(resolver, "_fetch_patch_text", fake_fetch_patch_text)
    selected_ref, payload, attempted_refs = resolver._fetch_patch_from_reference_candidates(
        [
            {
                "source_name": "linux-stable",
                "commit_id": "1234567",
                "patch_urls": ["https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/patch/?id=1234567"],
            },
            {
                "source_name": "upstream",
                "commit_id": "abcdef1",
                "patch_urls": ["https://github.com/torvalds/linux/commit/abcdef1.patch"],
            },
        ]
    )

    assert payload == "patch-body"
    assert selected_ref["source_name"] == "upstream"
    assert [item["source_name"] for item in attempted_refs] == ["linux-stable", "upstream"]


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
                "summary": {
                    "request_count": 1,
                    "success_count": 1,
                    "failure_count": 0,
                    "cache_hit_count": 0,
                    "stale_cache_hit_count": 0,
                },
            },
        },
    )

    bundle = service.fetch_patch_bundle(task=task, raw_patch_path=raw_patch_path)

    trace_path = task.workspace_dir / "analysis" / "trace" / "source_fetch_trace.json"
    assert bundle.stable_commit == "1234567"
    assert trace_path.exists()
    trace_payload = json.loads(trace_path.read_text(encoding="utf-8"))
    assert trace_payload["status"] == "passed"
