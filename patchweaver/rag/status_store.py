"""JSON-backed RAG import status storage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class RagImportStatusStore:
    """Persist the latest RAG import status as a small JSON document."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def read(self) -> dict[str, Any] | None:
        """Return the latest status payload, or None when no status exists."""

        if not self.path.exists():
            return None
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"RAG import status must be a JSON object: {self.path}")
        return payload

    def write(self, payload: dict[str, Any]) -> Path:
        """Write a status payload and return the status path."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp_path.replace(self.path)
        return self.path
