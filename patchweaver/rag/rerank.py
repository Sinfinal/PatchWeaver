"""Rerank client for DashScope-compatible APIs."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from patchweaver.config.models import RagConfig


class RerankClient:
    """Refine vector hits with a rerank model."""

    def __init__(self, config: RagConfig) -> None:
        self.config = config

    def rerank(
        self,
        *,
        query: str,
        documents: list[str],
        top_n: int,
    ) -> list[dict[str, Any]]:
        """Rerank the candidate documents for the given query."""

        if not documents:
            return []
        api_key = self.config.resolve_rerank_api_key()
        if not api_key:
            raise ValueError(
                f"Rerank API key is missing. Set environment variable {self.config.rerank_api_key_env}."
            )

        payload = {
            "model": self.config.rerank_model,
            "query": query,
            "documents": documents,
            "top_n": min(max(1, top_n), len(documents)),
            "return_documents": True,
        }
        request = Request(
            url=f"{self.config.rerank_base_url.rstrip('/')}/reranks",
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )
        try:
            with urlopen(request, timeout=self.config.rerank_timeout_sec) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ValueError(f"Rerank request failed: {exc.code} {detail}") from exc
        except URLError as exc:
            raise ValueError(f"Rerank request failed: {exc}") from exc

        data = json.loads(body)
        results = data.get("results") or data.get("data") or []
        normalized: list[dict[str, Any]] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            index = item.get("index")
            score = item.get("relevance_score", item.get("score"))
            document = item.get("document")
            if isinstance(document, dict):
                document = document.get("text")
            normalized.append(
                {
                    "index": int(index) if index is not None else -1,
                    "relevance_score": float(score) if score is not None else 0.0,
                    "document": str(document) if document is not None else None,
                }
            )
        return normalized
