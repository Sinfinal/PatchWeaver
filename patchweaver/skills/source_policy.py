"""Skill 来源策略。"""

from __future__ import annotations

from pathlib import Path

from patchweaver.config.loader import load_skills_config


def resolve_skill_roots(project_root: Path) -> list[tuple[str, Path]]:
    """按配置声明的优先级返回 skill 根目录。"""

    skills_config = load_skills_config(project_root)
    roots: dict[str, Path] = {
        "project": (project_root / skills_config.skill_dirs.project).resolve(),
        "shared": (project_root / skills_config.skill_dirs.shared).resolve(),
        "builtin": (project_root / skills_config.skill_dirs.builtin).resolve(),
        "workspace": (project_root / "workspaces" / "_shared_skills").resolve(),
    }
    return [(name, roots[name]) for name in skills_config.skill_source_priority if name in roots]

