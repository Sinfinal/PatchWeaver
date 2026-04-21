"""经验记忆仓库"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from patchweaver.models.memory import FailureMemoryEntry, RecipeMemoryEntry

ModelT = TypeVar("ModelT", bound=BaseModel)


class MemoryRepository:
    """负责经验条目的本地持久化"""

    def __init__(self, root_dir: Path) -> None:
        """初始化存储目录"""

        self.root_dir = root_dir
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.failure_path = self.root_dir / "failure_memory.json"
        self.recipe_path = self.root_dir / "recipe_memory.json"

    def load_failure_entries(self) -> list[FailureMemoryEntry]:
        """读取失败经验条目"""

        return self._load_entries(self.failure_path, FailureMemoryEntry)

    def save_failure_entries(self, entries: list[FailureMemoryEntry]) -> list[FailureMemoryEntry]:
        """写回失败经验条目"""

        return self._save_entries(self.failure_path, entries)

    def load_recipe_entries(self) -> list[RecipeMemoryEntry]:
        """读取配方经验条目"""

        return self._load_entries(self.recipe_path, RecipeMemoryEntry)

    def save_recipe_entries(self, entries: list[RecipeMemoryEntry]) -> list[RecipeMemoryEntry]:
        """写回配方经验条目"""

        return self._save_entries(self.recipe_path, entries)

    def snapshot(self) -> dict[str, object]:
        """返回当前双记忆快照"""

        failures = self.load_failure_entries()
        recipes = self.load_recipe_entries()
        return {
            "failure_memory": [entry.model_dump(mode="json") for entry in failures],
            "recipe_memory": [entry.model_dump(mode="json") for entry in recipes],
        }

    def _load_entries(self, path: Path, model_cls: type[ModelT]) -> list[ModelT]:
        """读取单类条目"""

        if not path.exists():
            return []
        raw = json.loads(path.read_text(encoding="utf-8") or "[]")
        if not isinstance(raw, list):
            return []
        return [model_cls.model_validate(item) for item in raw]

    def _save_entries(self, path: Path, entries: list[ModelT]) -> list[ModelT]:
        """保存单类条目"""

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps([entry.model_dump(mode="json") for entry in entries], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return entries
