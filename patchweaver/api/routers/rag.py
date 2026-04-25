"""RAG 检索接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from patchweaver.api.deps import ApiContext, get_api_context
from patchweaver.api.schemas import RagSearchRequest, RagSearchResponse
from patchweaver.api.services.rag_service import RagApiService

router = APIRouter(tags=["rag"])


@router.post("/rag/search", response_model=RagSearchResponse)
def search_rag(request: RagSearchRequest, context: ApiContext = Depends(get_api_context)) -> RagSearchResponse:
    """按查询语句检索修复知识卡切片。"""

    try:
        payload = RagApiService(context).search(
            query=request.query,
            limit=request.limit,
            cve_id=request.cve_id,
            subsystem=request.subsystem,
        )
        return RagSearchResponse(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
