"""环境诊断报告写入器。"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class DoctorWriter:
    """负责把 doctor 结果写入任务目录。"""

    def write(self, payload: dict[str, Any], target_path: Path) -> Path:
        """把 doctor 结果保存为 JSON 文件。"""

        target_path.parent.mkdir(parents=True, exist_ok=True)
        import json

        target_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return target_path

