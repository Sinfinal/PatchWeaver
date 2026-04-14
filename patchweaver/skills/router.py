"""Skill 路由。"""

from __future__ import annotations

from pathlib import Path

from patchweaver.models.skill import SkillManifest, SkillRouteDecision
from patchweaver.skills.registry import SkillRegistry
from patchweaver.skills.subagent_policy import SubagentPolicy


class SkillRouter:
    """根据阶段选择最合适的 skill。"""

    def __init__(self, project_root: Path) -> None:
        """创建一个面向当前项目的 skill 路由器。"""

        self.registry = SkillRegistry(project_root)
        self.subagent_policy = SubagentPolicy()

    def route(self, stage_name: str) -> SkillRouteDecision:
        """为指定阶段生成一份路由决策。"""

        manifests = self.registry.find_by_stage(stage_name)
        candidate_names = [manifest.skill_name for manifest in manifests]
        selected_manifest = manifests[0] if manifests else None
        selected = selected_manifest.skill_name if selected_manifest else None
        rejected = [self._rejected_reason(manifest) for manifest in manifests[1:]]
        contract_summary = self._contract_summary(selected_manifest) if selected_manifest is not None else []
        fallback_used = selected_manifest is None
        reason = (
            f"命中阶段优先级最高的可见 skill，来源={selected_manifest.source_layer}，只读={selected_manifest.readonly}。"
            if selected_manifest is not None
            else "当前阶段没有可用 skill，将回退到 direct_worker。"
        )
        return SkillRouteDecision(
            stage_name=stage_name,
            candidate_skills=candidate_names,
            selected_skill=selected,
            rejected_skills=rejected,
            selection_reason=reason,
            readonly_subagent_allowed=bool(
                selected_manifest
                and selected_manifest.allow_readonly_subagent
                and self.subagent_policy.allow(stage_name)
            ),
            contract_summary=contract_summary,
            fallback_used=fallback_used,
            route_source="fallback" if fallback_used else "registry",
        )

    def _rejected_reason(self, manifest: SkillManifest) -> str:
        """生成未选中 skill 的简要说明。"""

        return f"{manifest.skill_name}: 优先级更低或来源层级靠后。"

    def _contract_summary(self, manifest: SkillManifest) -> list[str]:
        """整理选中 skill 的输入输出契约摘要。"""

        summary: list[str] = []
        if manifest.input_contract:
            summary.append(f"输入: {', '.join(manifest.input_contract[:3])}")
        if manifest.output_contract:
            summary.append(f"输出: {', '.join(manifest.output_contract[:3])}")
        if manifest.tool_allowlist:
            summary.append(f"工具: {', '.join(manifest.tool_allowlist[:3])}")
        return summary
