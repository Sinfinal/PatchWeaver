"""RAG search service."""

from __future__ import annotations

from typing import Any

from patchweaver.config.models import RagConfig
from patchweaver.rag.embedding import EmbeddingClient
from patchweaver.rag.milvus_store import MilvusStore
from patchweaver.rag.rerank import RerankClient


class RagSearchService:
    """Semantic search entry for PatchWeaver RAG."""

    def __init__(self, config: RagConfig) -> None:
        self.config = config
        self.embedding_client = EmbeddingClient(config)
        self.store = MilvusStore(config)
        self.rerank_client = RerankClient(config)

    def search(
        self,
        *,
        query: str,
        limit: int | None = None,
        cve_id: str | None = None,
        subsystem: str | None = None,
    ) -> dict[str, Any]:
        """Run vector retrieval and optional rerank refinement."""

        if not self.config.enabled:
            raise ValueError("RAG search is disabled.")
        effective_limit = limit or self.config.search_limit
        candidate_limit = effective_limit
        if self.config.rerank_enabled:
            candidate_limit = max(effective_limit, self.config.rerank_candidate_pool, self.config.rerank_top_n)

        query_vector = self.embedding_client.embed_texts([query])[0]
        items = self.store.search(
            query_vector=query_vector,
            limit=candidate_limit,
            cve_id=cve_id,
            subsystem=subsystem,
        )
        rerank_applied = False
        rerank_model = None
        if self.config.rerank_enabled and len(items) > 1:
            items = self._rerank_items(query=query, items=items, limit=effective_limit)
            rerank_applied = True
            rerank_model = self.config.rerank_model
        else:
            items = items[:effective_limit]

        return {
            "query": query,
            "limit": effective_limit,
            "collection": self.config.milvus_collection,
            "rerank_applied": rerank_applied,
            "rerank_model": rerank_model,
            "items": items,
        }

    def _rerank_items(self, *, query: str, items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        documents = [str(item.get("text") or "") for item in items]
        reranked = self.rerank_client.rerank(
            query=query,
            documents=documents,
            top_n=min(limit, self.config.rerank_top_n, len(documents)),
        )
        reranked_items: list[dict[str, Any]] = []
        used_indexes: set[int] = set()
        for result in reranked:
            index = int(result.get("index", -1))
            if index < 0 or index >= len(items) or index in used_indexes:
                continue
            used_indexes.add(index)
            item = dict(items[index])
            item["vector_score"] = float(item.get("score", 0.0))
            item["rerank_score"] = float(result.get("relevance_score", 0.0))
            item["score"] = float(result.get("relevance_score", 0.0))
            reranked_items.append(item)
        if len(reranked_items) >= limit:
            return reranked_items[:limit]

        for index, item in enumerate(items):
            if index in used_indexes:
                continue
            fallback = dict(item)
            fallback["vector_score"] = float(fallback.get("score", 0.0))
            fallback["rerank_score"] = None
            reranked_items.append(fallback)
            if len(reranked_items) >= limit:
                break
        return reranked_items[:limit]
