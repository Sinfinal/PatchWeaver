"""JSON 报告写入器"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel
import json

from patchweaver.utils.path_policy import relativize_payload


class JsonWriter:
    """负责把结构化对象写成 JSON 文件"""

    def __init__(self, project_root: Path | None = None) -> None:
        """保存项目根目录，供路径序列化使用"""

        self.project_root = project_root.resolve() if project_root is not None else None

    def write_model(self, model: BaseModel, target_path: Path) -> Path:
        """把模型对象写到指定位置"""

        target_path.parent.mkdir(parents=True, exist_ok=True)
        payload = relativize_payload(model, self.project_root)
        target_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return target_path
