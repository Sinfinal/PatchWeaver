from __future__ import annotations

from patchweaver.retriever.repair_chain import RepairChainResolver


def test_fetch_nvd_record_falls_back_when_source_unavailable(monkeypatch) -> None:
    resolver = RepairChainResolver()

    def fake_fetch_json(url: str) -> dict[str, object]:
        raise ValueError(f"请求来源失败：{url} (503)")

    monkeypatch.setattr(resolver, "_fetch_json", fake_fetch_json)

    record = resolver._fetch_nvd_record("CVE-2024-1086")

    assert record["references"] == []
    assert "503" in str(record["_fetch_error"])
