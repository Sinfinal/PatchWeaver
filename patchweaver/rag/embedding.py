"""Embedding 客户端。"""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from patchweaver.config.models import RagConfig


class EmbeddingClient:
    """通过百炼兼容接口生成 embedding。"""

    def __init__(self, config: RagConfig) -> None:
        self.config = config

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量生成向量。"""

        if not texts:
            return []
        api_key = self.config.resolve_api_key()
        if not api_key:
            raise ValueError(
                f"未配置 embedding API Key，请设置环境变量 {self.config.embedding_api_key_env}。"
            )

        payload: dict[str, Any] = {
            "model": self.config.embedding_model,
            "input": texts,
        }
        if self.config.embedding_dimensions > 0:
            payload["dimensions"] = self.config.embedding_dimensions

        request = Request(
            url=f"{self.config.embedding_base_url.rstrip('/')}/embeddings",
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )
        try:
            with urlopen(request, timeout=self.config.embedding_timeout_sec) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ValueError(f"embedding 请求失败: {exc.code} {detail}") from exc
        except URLError as exc:
            raise ValueError(f"embedding 请求失败: {exc}") from exc

        data = json.loads(body)
        items = data.get("data") or []
        embeddings = [item.get("embedding") for item in items if isinstance(item, dict)]
        if len(embeddings) != len(texts):
            raise ValueError("embedding 返回数量与输入数量不一致。")
        return [[float(value) for value in embedding] for embedding in embeddings]
