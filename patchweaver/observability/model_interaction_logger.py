"""模型交互结构化记录写入器"""

from __future__ import annotations

import json
from pathlib import Path

from patchweaver.models.model_interaction import ModelInteractionRecord
from patchweaver.utils.path_policy import ensure_within_root, relativize_payload


class ModelInteractionLogger:
    """负责把模型调用留痕写入任务产物和全局 JSONL"""

    def __init__(self, project_root: Path, *, jsonl_path: str, record_mode: str) -> None:
        """保存项目根目录和模型交互记录配置"""

        self.project_root = project_root.resolve()
        self.record_mode = record_mode
        self.jsonl_path = ensure_within_root(self.project_root, jsonl_path, label="interaction_jsonl_path")

    def record(self, record: ModelInteractionRecord, *, artifact_path: Path | None = None) -> Path | None:
        """按当前模式写入单次模型交互记录"""

        if self.record_mode == "off":
            return None

        final_artifact_path: Path | None = None
        if artifact_path is not None:
            final_artifact_path = artifact_path.resolve()
            record = record.model_copy(update={"artifact_path": final_artifact_path.as_posix()})
            payload = relativize_payload(record, self.project_root)
            final_artifact_path.parent.mkdir(parents=True, exist_ok=True)
            final_artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        jsonl_payload = relativize_payload(record, self.project_root)
        with self.jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(jsonl_payload, ensure_ascii=False) + "\n")
        return final_artifact_path
