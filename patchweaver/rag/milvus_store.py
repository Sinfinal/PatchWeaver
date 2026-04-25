"""Milvus 向量库访问。"""

from __future__ import annotations

import json
from typing import Any

from patchweaver.config.models import RagConfig


def _escape_expr_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


class MilvusStore:
    """Milvus collection 封装。"""

    def __init__(self, config: RagConfig, *, alias: str = "patchweaver_rag") -> None:
        self.config = config
        self.alias = alias
        self._connected = False

    def _connect(self) -> None:
        if self._connected:
            return
        try:
            from pymilvus import connections
        except ImportError as exc:
            raise RuntimeError("未安装 pymilvus，请先执行 `pip install -e .`。") from exc

        kwargs: dict[str, Any] = {"alias": self.alias, "uri": self.config.milvus_uri}
        if self.config.milvus_token.strip():
            kwargs["token"] = self.config.milvus_token.strip()
        connections.connect(**kwargs)
        self._connected = True

    def ensure_collection(self, *, drop_existing: bool = False) -> None:
        """确保 collection 已创建。"""

        self._connect()
        from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, utility

        name = self.config.milvus_collection
        if utility.has_collection(name, using=self.alias):
            if not drop_existing:
                return
            utility.drop_collection(name, using=self.alias)

        fields = [
            FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=128),
            FieldSchema(name="cve_id", dtype=DataType.VARCHAR, max_length=32),
            FieldSchema(name="section", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="subsystem", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="card_path", dtype=DataType.VARCHAR, max_length=512),
            FieldSchema(name="metadata_json", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self.config.embedding_dimensions),
        ]
        schema = CollectionSchema(fields=fields, description="PatchWeaver CVE repair chunks")
        collection = Collection(name=name, schema=schema, using=self.alias)
        collection.create_index(
            field_name="embedding",
            index_params={
                "index_type": "HNSW",
                "metric_type": self.config.metric_type,
                "params": {"M": 16, "efConstruction": 200},
            },
        )
        collection.load()

    def insert_documents(self, docs: list[dict[str, Any]]) -> int:
        """批量写入文档。"""

        if not docs:
            return 0
        self._connect()
        from pymilvus import Collection

        collection = Collection(self.config.milvus_collection, using=self.alias)
        payload = [
            [doc["id"] for doc in docs],
            [doc["cve_id"] for doc in docs],
            [doc["section"] for doc in docs],
            [doc["subsystem"] for doc in docs],
            [doc["card_path"] for doc in docs],
            [doc["metadata_json"] for doc in docs],
            [doc["text"] for doc in docs],
            [doc["embedding"] for doc in docs],
        ]
        collection.insert(payload)
        collection.flush()
        return len(docs)

    def search(
        self,
        *,
        query_vector: list[float],
        limit: int,
        cve_id: str | None = None,
        subsystem: str | None = None,
    ) -> list[dict[str, Any]]:
        """执行向量检索。"""

        self._connect()
        from pymilvus import Collection

        collection = Collection(self.config.milvus_collection, using=self.alias)
        collection.load()
        expr_parts: list[str] = []
        if cve_id:
            expr_parts.append(f'cve_id == "{_escape_expr_value(cve_id)}"')
        if subsystem:
            expr_parts.append(f'subsystem == "{_escape_expr_value(subsystem)}"')
        expr = " and ".join(expr_parts) if expr_parts else None

        results = collection.search(
            data=[query_vector],
            anns_field="embedding",
            limit=limit,
            param={"metric_type": self.config.metric_type, "params": {"ef": max(64, limit * 8)}},
            expr=expr,
            output_fields=["cve_id", "section", "subsystem", "card_path", "metadata_json", "text"],
        )
        hits: list[dict[str, Any]] = []
        for hit in results[0]:
            entity = getattr(hit, "entity", None)
            metadata_json = entity.get("metadata_json") if entity is not None else "{}"
            try:
                metadata = json.loads(metadata_json) if metadata_json else {}
            except json.JSONDecodeError:
                metadata = {}
            hits.append(
                {
                    "chunk_id": str(hit.id),
                    "cve_id": entity.get("cve_id") if entity is not None else "",
                    "section": entity.get("section") if entity is not None else "",
                    "subsystem": entity.get("subsystem") if entity is not None else None,
                    "score": float(getattr(hit, "distance", getattr(hit, "score", 0.0))),
                    "text": entity.get("text") if entity is not None else "",
                    "card_path": entity.get("card_path") if entity is not None else None,
                    "metadata": metadata,
                }
            )
        return hits
