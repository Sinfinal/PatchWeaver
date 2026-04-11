"""Skill 路由。"""

from __future__ import annotations

from pathlib import Path

from patchweaver.models.skill import SkillRouteDecision
from patchweaver.skills.registry import SkillRegistry


class SkillRouter:
    """根据阶段选择最合适的 skill。"""

    def __init__(self, project_root: Path) -> None:
        """创建一个面向当前项目的 skill 路由器。"""

        self.registry = SkillRegistry(project_root)

    def route(self, stage_name: str) -> SkillRouteDecision:
        """为指定阶段生成一份路由决策。"""

        manifests = self.registry.find_by_stage(stage_name)
        candidate_names = [manifest.skill_name for manifest in manifests]
        selected = manifests[0].skill_name if manifests else None
        reason = "命中阶段优先级最高的可见 skill。" if selected else "当前阶段没有可用 skill。"
        return SkillRouteDecision(
            stage_name=stage_name,
            candidate_skills=candidate_names,
            selected_skill=selected,
            selection_reason=reason,
            fallback_used=False,
            route_source="registry",
        )

