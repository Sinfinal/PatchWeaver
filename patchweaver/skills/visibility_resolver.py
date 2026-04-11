"""Skill 可见性解析。"""

from __future__ import annotations

from patchweaver.models.skill import SkillManifest


class VisibilityResolver:
    """负责判断 skill 在当前场景下是否可见。"""

    def is_visible(self, manifest: SkillManifest) -> bool:
        """根据 manifest 给出最小可见性判断。"""

        return manifest.visibility in {"project", "shared", "builtin", "workspace"}

