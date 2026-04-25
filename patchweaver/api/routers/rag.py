"""RAG routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from patchweaver.api.deps import ApiContext, get_api_context
from patchweaver.api.schemas import (
    RagHealthResponse,
    RagImportStatusResponse,
    RagReindexRequest,
    RagReindexResponse,
    RagSearchRequest,
    RagSearchResponse,
    RagStatsResponse,
)
from patchweaver.api.services.rag_service import RagApiService

router = APIRouter(tags=["rag"])


@router.post("/rag/search", response_model=RagSearchResponse)
def search_rag(request: RagSearchRequest, context: ApiContext = Depends(get_api_context)) -> RagSearchResponse:
    """Search the current RAG collection."""

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


@router.get("/rag/health", response_model=RagHealthResponse)
def health_rag(context: ApiContext = Depends(get_api_context)) -> RagHealthResponse:
    """Return the current RAG backend health snapshot."""

    payload = RagApiService(context).health()
    return RagHealthResponse(**payload)


@router.get("/rag/stats", response_model=RagStatsResponse)
def get_rag_stats(context: ApiContext = Depends(get_api_context)) -> RagStatsResponse:
    """Return the current RAG backend statistics."""

    payload = RagApiService(context).stats()
    return RagStatsResponse(**payload)


@router.get("/rag/import-status", response_model=RagImportStatusResponse)
def get_rag_import_status(context: ApiContext = Depends(get_api_context)) -> RagImportStatusResponse:
    """Return the latest RAG import status snapshot."""

    payload = RagApiService(context).import_status()
    return RagImportStatusResponse(**payload)


@router.post("/rag/reindex", response_model=RagReindexResponse)
def reindex_rag(request: RagReindexRequest, context: ApiContext = Depends(get_api_context)) -> RagReindexResponse:
    """Rebuild the active RAG collection from the configured corpus."""

    try:
        payload = RagApiService(context).reindex(
            corpus_path=request.corpus_path,
            drop_existing=request.drop_existing,
        )
        return RagReindexResponse(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
