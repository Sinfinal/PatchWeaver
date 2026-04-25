"""RAG API 服务。"""

from __future__ import annotations

from patchweaver.api.deps import ApiContext
from patchweaver.rag.search_service import RagSearchService


class RagApiService:
    """封装 API 侧的 RAG 检索调用。"""

    def __init__(self, context: ApiContext) -> None:
        self.context = context
        self.service = RagSearchService(context.rag_config)

    def search(
        self,
        *,
        query: str,
        limit: int | None = None,
        cve_id: str | None = None,
        subsystem: str | None = None,
    ) -> dict:
        return self.service.search(
            query=query,
            limit=limit,
            cve_id=cve_id,
            subsystem=subsystem,
        )
