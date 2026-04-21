"""Trace 写入器"""

from __future__ import annotations

import json
from pathlib import Path

from patchweaver.models.harness import HarnessTrace
from patchweaver.utils.path_policy import relativize_payload


class TraceWriter:
    """负责把 trace 按文件形式落盘"""

    def __init__(self, project_root: Path | None = None) -> None:
        """保存项目根目录，供路径序列化使用"""

        self.project_root = project_root.resolve() if project_root is not None else None

    def write(self, trace: HarnessTrace, target_path: Path) -> Path:
        """把 trace 写到指定路径"""

        target_path.parent.mkdir(parents=True, exist_ok=True)
        payload = relativize_payload(trace, self.project_root)
        target_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return target_path
