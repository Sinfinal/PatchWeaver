"""RAG API services."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from patchweaver.api.deps import ApiContext
from patchweaver.rag.importer import RagImporter
from patchweaver.rag.milvus_store import MilvusStore
from patchweaver.rag.search_service import RagSearchService
from patchweaver.rag.status_store import RagImportStatusStore
from patchweaver.utils.path_policy import ensure_within_root, to_project_relative


class RagApiService:
    """Facade used by the RAG API routes."""

    def __init__(self, context: ApiContext) -> None:
        self.context = context
        self.config = context.rag_config
        self.search_service = RagSearchService(self.config)
        self.store = MilvusStore(self.config)
        self.importer = RagImporter(self.config)
        self.status_store = RagImportStatusStore(context.runtime.manifest_dir / "rag_import_status.json")

    def search(
        self,
        *,
        query: str,
        limit: int | None = None,
        cve_id: str | None = None,
        subsystem: str | None = None,
    ) -> dict:
        return self.search_service.search(
            query=query,
            limit=limit,
            cve_id=cve_id,
            subsystem=subsystem,
        )

    def health(self) -> dict:
        payload = {
            "status": "disabled" if not self.config.enabled else "ok",
            "enabled": self.config.enabled,
            "backend": self.config.vector_backend,
            "milvus_uri": self.config.milvus_uri,
            "milvus_database": self.config.milvus_database,
            "collection": self.config.milvus_collection,
            "connection_ready": False,
            "collection_exists": False,
            "api_key_ready": self.config.resolve_api_key() is not None,
            "embedding_model": self.config.embedding_model,
            "embedding_dimensions": self.config.embedding_dimensions,
            "rerank_enabled": self.config.rerank_enabled,
            "rerank_model": self.config.rerank_model if self.config.rerank_enabled else None,
            "rerank_api_key_ready": self.config.resolve_rerank_api_key() is not None,
            "detail": None,
        }
        if not self.config.enabled:
            return payload

        try:
            payload["connection_ready"] = self.store.ping()
            payload["collection_exists"] = self.store.collection_exists()
        except Exception as exc:
            payload["status"] = "error"
            payload["detail"] = str(exc)
        return payload

    def stats(self) -> dict:
        corpus_path = self._resolve_corpus_path()
        import_status = self.import_status()
        payload = {
            "status": "disabled" if not self.config.enabled else "ok",
            "enabled": self.config.enabled,
            "backend": self.config.vector_backend,
            "milvus_uri": self.config.milvus_uri,
            "milvus_database": self.config.milvus_database,
            "collection": self.config.milvus_collection,
            "collection_exists": False,
            "document_count": 0,
            "default_search_limit": self.config.search_limit,
            "metric_type": self.config.metric_type,
            "embedding_model": self.config.embedding_model,
            "embedding_dimensions": self.config.embedding_dimensions,
            "rerank_enabled": self.config.rerank_enabled,
            "rerank_model": self.config.rerank_model if self.config.rerank_enabled else None,
            "rerank_candidate_pool": self.config.rerank_candidate_pool,
            "rerank_top_n": self.config.rerank_top_n,
            "default_corpus_path": self._to_project_path(corpus_path),
            "status_path": import_status["status_path"],
            "last_import_status": import_status.get("status"),
            "last_import_at": import_status.get("updated_at"),
            "detail": None,
        }
        if not self.config.enabled:
            return payload

        try:
            payload["collection_exists"] = self.store.collection_exists()
            payload["document_count"] = self.store.count_documents() if payload["collection_exists"] else 0
        except Exception as exc:
            payload["status"] = "error"
            payload["document_count"] = None
            payload["detail"] = str(exc)
        return payload

    def import_status(self) -> dict:
        status_path = self._to_project_path(self.status_store.path)
        try:
            payload = self.status_store.read()
        except Exception as exc:
            return {
                "available": True,
                "status_path": status_path,
                "status": "error",
                "updated_at": None,
                "collection": self.config.milvus_collection,
                "source_path": None,
                "imported": None,
                "drop_existing": None,
                "detail": "Failed to read the latest RAG import status.",
                "error": str(exc),
            }

        if payload is None:
            return {
                "available": False,
                "status_path": status_path,
                "status": None,
                "updated_at": None,
                "collection": None,
                "source_path": None,
                "imported": None,
                "drop_existing": None,
                "detail": None,
                "error": None,
            }

        source_path = payload.get("source_path")
        if source_path:
            source_path = self._to_project_path(Path(str(source_path)))
        return {
            "available": True,
            "status_path": status_path,
            "status": payload.get("status"),
            "updated_at": payload.get("updated_at"),
            "collection": payload.get("collection"),
            "source_path": source_path,
            "imported": payload.get("imported"),
            "drop_existing": payload.get("drop_existing"),
            "detail": payload.get("detail"),
            "error": payload.get("error"),
        }

    def reindex(self, *, corpus_path: str | None = None, drop_existing: bool = True) -> dict:
        resolved_corpus_path = self._resolve_corpus_path(corpus_path)
        source_path = self._to_project_path(resolved_corpus_path)
        started_at = self._timestamp()
        self.status_store.write(
            {
                "status": "running",
                "updated_at": started_at,
                "collection": self.config.milvus_collection,
                "source_path": source_path,
                "imported": None,
                "drop_existing": drop_existing,
                "detail": "RAG corpus import is running.",
                "error": None,
            }
        )

        try:
            result = self.importer.import_jsonl(resolved_corpus_path, drop_existing=drop_existing)
        except Exception as exc:
            failed_at = self._timestamp()
            self.status_store.write(
                {
                    "status": "failed",
                    "updated_at": failed_at,
                    "collection": self.config.milvus_collection,
                    "source_path": source_path,
                    "imported": None,
                    "drop_existing": drop_existing,
                    "detail": "RAG corpus import failed.",
                    "error": str(exc),
                }
            )
            raise

        completed_at = self._timestamp()
        status_path = self.status_store.write(
            {
                "status": "completed",
                "updated_at": completed_at,
                "collection": str(result["collection"]),
                "source_path": source_path,
                "imported": int(result["imported"]),
                "drop_existing": drop_existing,
                "detail": "RAG corpus import completed.",
                "error": None,
            }
        )
        return {
            "status": "completed",
            "status_path": self._to_project_path(status_path),
            "updated_at": completed_at,
            "collection": str(result["collection"]),
            "source_path": source_path,
            "imported": int(result["imported"]),
            "drop_existing": drop_existing,
            "detail": "RAG corpus import completed.",
        }

    def _resolve_corpus_path(self, raw_path: str | None = None) -> Path:
        selected_path = raw_path.strip() if raw_path and raw_path.strip() else self.config.corpus_jsonl_path
        return ensure_within_root(self.context.project_root, selected_path, label="corpus_path")

    def _timestamp(self) -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    def _to_project_path(self, path: Path) -> str:
        return str(to_project_relative(self.context.project_root, path))
