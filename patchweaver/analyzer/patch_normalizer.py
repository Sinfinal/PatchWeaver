"""Patch 规范化骨架。"""

from __future__ import annotations

from pathlib import Path


class PatchNormalizer:
    """负责管理原始补丁到规范化补丁的转换入口。"""

    def normalize(self, raw_patch_path: Path, normalized_patch_path: Path) -> Path:
        """返回规范化补丁路径。"""

        normalized_patch_path.parent.mkdir(parents=True, exist_ok=True)
        normalized_patch_path.write_text(raw_patch_path.read_text(encoding="utf-8"), encoding="utf-8")
        return normalized_patch_path

