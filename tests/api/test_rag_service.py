from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from patchweaver.api.services.rag_service import RagApiService
from patchweaver.config.models import RagConfig


def _build_context(tmp_path: Path, config: RagConfig | None = None):
    project_root = tmp_path / "project"
    manifest_dir = project_root / "data" / "manifests"
    project_root.mkdir(parents=True, exist_ok=True)
    manifest_dir.mkdir(parents=True, exist_ok=True)
    rag_config = config or RagConfig()
    return SimpleNamespace(
        project_root=project_root,
        runtime=SimpleNamespace(manifest_dir=manifest_dir),
        rag_config=rag_config,
    )


def test_rag_api_service_health_and_stats_report_runtime_state(monkeypatch, tmp_path: Path) -> None:
    context = _build_context(
        tmp_path,
        RagConfig(
            corpus_jsonl_path="rag_corpus_batch200/chunks/all_chunks.jsonl",
            milvus_collection="patchweaver_cve_chunks",
            milvus_database="default",
            milvus_uri="http://127.0.0.1:19530",
            metric_type="COSINE",
            search_limit=6,
            embedding_model="text-embedding-v3",
            embedding_dimensions=1024,
            rerank_enabled=True,
            rerank_model="qwen3-rerank",
            rerank_candidate_pool=12,
            rerank_top_n=6,
        ),
    )
    corpus_path = context.project_root / "rag_corpus_batch200" / "chunks" / "all_chunks.jsonl"
    corpus_path.parent.mkdir(parents=True, exist_ok=True)
    corpus_path.write_text("{\"chunk_id\":\"demo\"}\n", encoding="utf-8")
    (context.runtime.manifest_dir / "rag_import_status.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "updated_at": "2026-04-25T18:30:00+08:00",
                "collection": "patchweaver_cve_chunks",
                "source_path": "rag_corpus_batch200/chunks/all_chunks.jsonl",
                "imported": 42,
                "drop_existing": True,
                "detail": "RAG corpus import completed.",
                "error": None,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    class _StoreStub:
        def __init__(self, config):
            self.config = config

        def ping(self) -> bool:
            return True

        def collection_exists(self) -> bool:
            return True

        def count_documents(self) -> int:
            return 42

    monkeypatch.setattr("patchweaver.api.services.rag_service.MilvusStore", _StoreStub)

    service = RagApiService(context)
    health = service.health()
    stats = service.stats()
    import_status = service.import_status()

    assert health["status"] == "ok"
    assert health["connection_ready"] is True
    assert health["collection_exists"] is True
    assert health["rerank_enabled"] is True
    assert health["rerank_model"] == "qwen3-rerank"
    assert stats["status"] == "ok"
    assert stats["document_count"] == 42
    assert stats["last_import_status"] == "completed"
    assert stats["default_corpus_path"] == "rag_corpus_batch200/chunks/all_chunks.jsonl"
    assert stats["rerank_enabled"] is True
    assert stats["rerank_model"] == "qwen3-rerank"
    assert import_status["available"] is True
    assert import_status["imported"] == 42
    assert import_status["source_path"] == "rag_corpus_batch200/chunks/all_chunks.jsonl"


def test_rag_api_service_reindex_writes_latest_status(monkeypatch, tmp_path: Path) -> None:
    context = _build_context(
        tmp_path,
        RagConfig(
            corpus_jsonl_path="rag_corpus_batch200/chunks/all_chunks.jsonl",
            milvus_collection="patchweaver_cve_chunks",
        ),
    )
    corpus_path = context.project_root / "rag_corpus_batch200" / "chunks" / "all_chunks.jsonl"
    corpus_path.parent.mkdir(parents=True, exist_ok=True)
    corpus_path.write_text("{\"chunk_id\":\"demo\"}\n", encoding="utf-8")

    class _ImporterStub:
        def __init__(self, config):
            self.config = config

        def import_jsonl(self, import_path: Path, *, drop_existing: bool = False) -> dict[str, object]:
            return {
                "collection": self.config.milvus_collection,
                "imported": 12,
                "source_path": str(import_path),
            }

    monkeypatch.setattr("patchweaver.api.services.rag_service.RagImporter", _ImporterStub)

    service = RagApiService(context)
    payload = service.reindex(drop_existing=True)
    status_payload = json.loads((context.runtime.manifest_dir / "rag_import_status.json").read_text(encoding="utf-8"))

    assert payload["status"] == "completed"
    assert payload["collection"] == "patchweaver_cve_chunks"
    assert payload["imported"] == 12
    assert payload["source_path"] == "rag_corpus_batch200/chunks/all_chunks.jsonl"
    assert status_payload["status"] == "completed"
    assert status_payload["drop_existing"] is True
    assert status_payload["source_path"] == "rag_corpus_batch200/chunks/all_chunks.jsonl"
