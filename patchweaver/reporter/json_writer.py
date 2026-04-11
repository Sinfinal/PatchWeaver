"""JSON 报告写入器。"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel


class JsonWriter:
    """负责把结构化对象写成 JSON 文件。"""

    def write_model(self, model: BaseModel, target_path: Path) -> Path:
        """把模型对象写到指定位置。"""

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(model.model_dump_json(indent=2), encoding="utf-8")
        return target_path

