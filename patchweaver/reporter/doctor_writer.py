"""环境诊断报告写入器"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from patchweaver.utils.path_policy import relativize_payload


class DoctorWriter:
    """负责把 doctor 结果写入任务目录"""

    def __init__(self, project_root: Path | None = None) -> None:
        """保存项目根目录，供路径序列化使用"""

        self.project_root = project_root.resolve() if project_root is not None else None

    def write(self, payload: dict[str, Any], target_path: Path) -> Path:
        """把 doctor 结果保存为 JSON 文件"""

        target_path.parent.mkdir(parents=True, exist_ok=True)
        normalized = relativize_payload(payload, self.project_root)
        target_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return target_path
