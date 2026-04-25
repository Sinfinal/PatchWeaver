"""RAG 检索服务。"""

from __future__ import annotations

from typing import Any

from patchweaver.config.models import RagConfig
from patchweaver.rag.embedding import EmbeddingClient
from patchweaver.rag.milvus_store import MilvusStore


class RagSearchService:
    """语义检索入口。"""

    def __init__(self, config: RagConfig) -> None:
        self.config = config
        self.embedding_client = EmbeddingClient(config)
        self.store = MilvusStore(config)

    def search(
        self,
        *,
        query: str,
        limit: int | None = None,
        cve_id: str | None = None,
        subsystem: str | None = None,
    ) -> dict[str, Any]:
        """执行向量召回。"""

        if not self.config.enabled:
            raise ValueError("RAG 检索当前未启用。")
        effective_limit = limit or self.config.search_limit
        query_vector = self.embedding_client.embed_texts([query])[0]
        items = self.store.search(
            query_vector=query_vector,
            limit=effective_limit,
            cve_id=cve_id,
            subsystem=subsystem,
        )
        return {
            "query": query,
            "limit": effective_limit,
            "collection": self.config.milvus_collection,
            "items": items,
        }
