"""Skill 包加载器。"""

from __future__ import annotations

from pathlib import Path


class SkillPackLoader:
    """负责读取 skill 目录中的附加资源。"""

    def list_resources(self, skill_dir: Path) -> list[Path]:
        """返回当前 skill 目录下的资源文件。"""

        if not skill_dir.exists():
            return []
        return sorted(path for path in skill_dir.iterdir() if path.is_file())

