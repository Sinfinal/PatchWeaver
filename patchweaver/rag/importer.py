"""RAG 语料导入器。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from patchweaver.config.models import RagConfig
from patchweaver.rag.embedding import EmbeddingClient
from patchweaver.rag.milvus_store import MilvusStore


class RagImporter:
    """将 JSONL 语料导入 Milvus。"""

    def __init__(self, config: RagConfig) -> None:
        self.config = config
        self.embedding_client = EmbeddingClient(config)
        self.store = MilvusStore(config)

    def import_jsonl(self, corpus_path: Path, *, drop_existing: bool = False) -> dict[str, Any]:
        """导入切片语料。"""

        if not corpus_path.exists():
            raise FileNotFoundError(f"语料文件不存在: {corpus_path}")

        docs = [json.loads(line) for line in corpus_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.store.ensure_collection(drop_existing=drop_existing)

        total = 0
        batch_size = self.config.import_batch_size
        for start in range(0, len(docs), batch_size):
            chunk = docs[start : start + batch_size]
            vectors = self.embedding_client.embed_texts([item["text"] for item in chunk])
            payload: list[dict[str, Any]] = []
            for item, vector in zip(chunk, vectors, strict=True):
                metadata = item.get("metadata") or {}
                payload.append(
                    {
                        "id": str(item["chunk_id"]),
                        "cve_id": str(item["cve_id"]),
                        "section": str(item.get("section") or ""),
                        "subsystem": str(metadata.get("subsystem") or "unknown"),
                        "card_path": str(item.get("card_path") or ""),
                        "metadata_json": json.dumps(metadata, ensure_ascii=False),
                        "text": str(item["text"]),
                        "embedding": vector,
                    }
                )
            total += self.store.insert_documents(payload)

        return {
            "collection": self.config.milvus_collection,
            "imported": total,
            "source_path": str(corpus_path),
        }
