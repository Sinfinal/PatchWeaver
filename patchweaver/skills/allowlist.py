"""Skill allowlist 规则。"""

from __future__ import annotations

from pathlib import Path

from patchweaver.config.loader import load_skills_config
from patchweaver.models.skill import SkillManifest


def is_skill_allowed(project_root: Path, manifest: SkillManifest) -> bool:
    """判断 skill 是否满足当前 allowlist 规则。"""

    skills_config = load_skills_config(project_root)
    if not skills_config.enforce_allowlist:
        return True
    if not manifest.allowed_tags:
        return False
    return any(tag in skills_config.allowed_skill_tags for tag in manifest.allowed_tags)

