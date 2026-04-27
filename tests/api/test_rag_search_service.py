from __future__ import annotations

from patchweaver.config.models import RagConfig
from patchweaver.rag.search_service import RagSearchService


def test_rag_search_service_applies_rerank(monkeypatch) -> None:
    config = RagConfig(
        search_limit=2,
        rerank_enabled=True,
        rerank_model="qwen3-rerank",
        rerank_candidate_pool=4,
        rerank_top_n=2,
    )

    class _EmbeddingStub:
        def __init__(self, config):
            self.config = config

        def embed_texts(self, texts: list[str]) -> list[list[float]]:
            return [[0.1, 0.2, 0.3]]

    class _StoreStub:
        def __init__(self, config):
            self.config = config

        def search(self, *, query_vector, limit, cve_id=None, subsystem=None):
            assert limit == 4
            return [
                {"chunk_id": "1", "cve_id": "CVE-1", "section": "A", "score": 0.21, "text": "alpha", "metadata": {}},
                {"chunk_id": "2", "cve_id": "CVE-2", "section": "B", "score": 0.42, "text": "beta", "metadata": {}},
                {"chunk_id": "3", "cve_id": "CVE-3", "section": "C", "score": 0.63, "text": "gamma", "metadata": {}},
                {"chunk_id": "4", "cve_id": "CVE-4", "section": "D", "score": 0.84, "text": "delta", "metadata": {}},
            ]

    class _RerankStub:
        def __init__(self, config):
            self.config = config

        def rerank(self, *, query: str, documents: list[str], top_n: int):
            assert query == "netfilter verdict validation"
            assert documents == ["alpha", "beta", "gamma", "delta"]
            assert top_n == 2
            return [
                {"index": 2, "relevance_score": 0.97, "document": "gamma"},
                {"index": 1, "relevance_score": 0.88, "document": "beta"},
            ]

    monkeypatch.setattr("patchweaver.rag.search_service.EmbeddingClient", _EmbeddingStub)
    monkeypatch.setattr("patchweaver.rag.search_service.MilvusStore", _StoreStub)
    monkeypatch.setattr("patchweaver.rag.search_service.RerankClient", _RerankStub)

    payload = RagSearchService(config).search(query="netfilter verdict validation", limit=2)

    assert payload["rerank_applied"] is True
    assert payload["rerank_model"] == "qwen3-rerank"
    assert [item["chunk_id"] for item in payload["items"]] == ["3", "2"]
    assert payload["items"][0]["vector_score"] == 0.63
    assert payload["items"][0]["rerank_score"] == 0.97


def test_rag_search_service_skips_rerank_when_disabled(monkeypatch) -> None:
    config = RagConfig(search_limit=2, rerank_enabled=False)

    class _EmbeddingStub:
        def __init__(self, config):
            self.config = config

        def embed_texts(self, texts: list[str]) -> list[list[float]]:
            return [[0.1, 0.2, 0.3]]

    class _StoreStub:
        def __init__(self, config):
            self.config = config

        def search(self, *, query_vector, limit, cve_id=None, subsystem=None):
            assert limit == 2
            return [
                {"chunk_id": "1", "cve_id": "CVE-1", "section": "A", "score": 0.21, "text": "alpha", "metadata": {}},
                {"chunk_id": "2", "cve_id": "CVE-2", "section": "B", "score": 0.42, "text": "beta", "metadata": {}},
            ]

    class _RerankStub:
        def __init__(self, config):
            self.config = config

        def rerank(self, *, query: str, documents: list[str], top_n: int):
            raise AssertionError("rerank should not be called when disabled")

    monkeypatch.setattr("patchweaver.rag.search_service.EmbeddingClient", _EmbeddingStub)
    monkeypatch.setattr("patchweaver.rag.search_service.MilvusStore", _StoreStub)
    monkeypatch.setattr("patchweaver.rag.search_service.RerankClient", _RerankStub)

    payload = RagSearchService(config).search(query="netfilter verdict validation", limit=2)

    assert payload["rerank_applied"] is False
    assert payload["rerank_model"] is None
    assert [item["chunk_id"] for item in payload["items"]] == ["1", "2"]
