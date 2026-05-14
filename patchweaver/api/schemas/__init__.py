"""Request and response models used by the Web API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from patchweaver.api.schemas.chat import ChatRequest, ChatResponse, SuggestedAction, ToolCallTrace


class CreateTaskRequest(BaseModel):
    """Request payload for creating a task."""

    cve_id: str
    target_kernel: str | None = None
    profile: str | None = None
    max_attempts: int | None = None
    note: str | None = None
    force_new: bool = False
    auto_run: bool = False


class TaskActionResponse(BaseModel):
    """Common response for task actions."""

    task_id: str
    status: str
    detail: dict[str, Any] = Field(default_factory=dict)


class ArtifactContentResponse(BaseModel):
    """Preview payload for a single artifact file."""

    task_id: str
    relative_path: str
    project_path: str
    content: str
    content_type: str
    truncated: bool = False
    size: int | None = None


class HealthResponse(BaseModel):
    """Minimal service health response."""

    status: str
    version: str


class RagSearchRequest(BaseModel):
    """RAG search request."""

    query: str
    limit: int | None = None
    cve_id: str | None = None
    subsystem: str | None = None


class RagSearchHit(BaseModel):
    """Single RAG search hit."""

    chunk_id: str
    cve_id: str
    section: str
    subsystem: str | None = None
    score: float
    vector_score: float | None = None
    rerank_score: float | None = None
    text: str
    card_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RagSearchResponse(BaseModel):
    """RAG search response."""

    query: str
    limit: int
    collection: str
    rerank_applied: bool = False
    rerank_model: str | None = None
    items: list[RagSearchHit] = Field(default_factory=list)


class RagHealthResponse(BaseModel):
    """RAG backend health snapshot."""

    status: str
    enabled: bool
    backend: str
    milvus_uri: str
    milvus_database: str
    collection: str
    connection_ready: bool
    collection_exists: bool
    api_key_ready: bool
    embedding_model: str
    embedding_dimensions: int
    rerank_enabled: bool
    rerank_model: str | None = None
    rerank_api_key_ready: bool = False
    detail: str | None = None


class RagStatsResponse(BaseModel):
    """RAG backend statistics."""

    status: str
    enabled: bool
    backend: str
    milvus_uri: str
    milvus_database: str
    collection: str
    collection_exists: bool
    document_count: int | None = None
    default_search_limit: int
    metric_type: str
    embedding_model: str
    embedding_dimensions: int
    rerank_enabled: bool
    rerank_model: str | None = None
    rerank_candidate_pool: int
    rerank_top_n: int
    default_corpus_path: str
    status_path: str
    last_import_status: str | None = None
    last_import_at: str | None = None
    detail: str | None = None


class RagImportStatusResponse(BaseModel):
    """Latest RAG import status snapshot."""

    available: bool
    status_path: str
    status: str | None = None
    updated_at: str | None = None
    collection: str | None = None
    source_path: str | None = None
    imported: int | None = None
    drop_existing: bool | None = None
    detail: str | None = None
    error: str | None = None


class RagReindexRequest(BaseModel):
    """Request payload for rebuilding the active RAG collection."""

    corpus_path: str | None = None
    drop_existing: bool = True


class RagReindexResponse(BaseModel):
    """Response payload for rebuilding the active RAG collection."""

    status: str
    status_path: str
    updated_at: str
    collection: str
    source_path: str
    imported: int
    drop_existing: bool
    detail: str | None = None


__all__ = [
    "ArtifactContentResponse",
    "ChatRequest",
    "ChatResponse",
    "CreateTaskRequest",
    "HealthResponse",
    "RagHealthResponse",
    "RagImportStatusResponse",
    "RagReindexRequest",
    "RagReindexResponse",
    "RagSearchHit",
    "RagSearchRequest",
    "RagSearchResponse",
    "RagStatsResponse",
    "SuggestedAction",
    "TaskActionResponse",
    "ToolCallTrace",
]
