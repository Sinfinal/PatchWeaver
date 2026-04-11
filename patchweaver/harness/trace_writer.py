"""Trace 写入器。"""

from __future__ import annotations

from pathlib import Path

from patchweaver.models.harness import HarnessTrace


class TraceWriter:
    """负责把 trace 按文件形式落盘。"""

    def write(self, trace: HarnessTrace, target_path: Path) -> Path:
        """把 trace 写到指定路径。"""

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(trace.model_dump_json(indent=2), encoding="utf-8")
        return target_path

