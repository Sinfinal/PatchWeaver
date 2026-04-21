"""Skill 路由"""

from __future__ import annotations

from pathlib import Path

from patchweaver.config.loader import load_skills_config
from patchweaver.config.models import SkillsConfig
from patchweaver.models.skill import SkillManifest, SkillRouteDecision
from patchweaver.skills.registry import SkillRegistry
from patchweaver.skills.subagent_policy import SubagentPolicy


class SkillRouter:
    """根据阶段选择最合适的 skill"""

    def __init__(self, project_root: Path, *, skills_config: SkillsConfig | None = None) -> None:
        """创建一个面向当前项目的 skill 路由器"""

        self.registry = SkillRegistry(project_root)
        self.skills_config = skills_config or load_skills_config(project_root)
        self.active_profile = self.skills_config.skill_profiles.get(self.skills_config.default_skill_profile)
        self.subagent_policy = SubagentPolicy(
            allow_readonly_subagent=self.active_profile.allow_readonly_subagent if self.active_profile is not None else True,
            allowed_stages=self.active_profile.subagent_allowed_stages if self.active_profile is not None else None,
            max_parallel=self.active_profile.subagent_max_parallel if self.active_profile is not None else 2,
        )

    def route(self, stage_name: str) -> SkillRouteDecision:
        """为指定阶段生成一份路由决策"""

        if self.active_profile is not None and not self.active_profile.enable_skill_router:
            return SkillRouteDecision(
                stage_name=stage_name,
                candidate_skills=[],
                selected_skill=None,
                rejected_skills=[],
                selection_reason="当前 skill profile 已关闭 skill 路由，直接回退到 direct_worker。",
                readonly_subagent_allowed=False,
                contract_summary=[f"回退模式: {self.active_profile.fallback_dispatch}"],
                fallback_used=True,
                route_source="profile_disabled",
            )

        # 当前实现先按 registry 的阶段命中结果取第一优先级
        # 后面即使要扩成多指标排序，也可以继续沿用这个决策出口
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
            else f"当前阶段没有可用 skill，将回退到 {self._fallback_dispatch()}。"
        )
        if self.active_profile is not None:
            contract_summary.append(f"调度模式: {self.active_profile.preferred_dispatch}")
        if selected_manifest is not None and self.subagent_policy.allow(stage_name):
            # 子代理是否允许不是只看 skill 自身声明
            # 还要再过一层全局 profile 策略，避免阶段边界被绕开
            contract_summary.append(f"只读子代理并发上限: {self.subagent_policy.max_parallel}")
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

    def _fallback_dispatch(self) -> str:
        """返回当前 skill profile 的回退模式"""

        if self.active_profile is None:
            return "direct_worker"
        return self.active_profile.fallback_dispatch

    def _rejected_reason(self, manifest: SkillManifest) -> str:
        """生成未选中 skill 的简要说明"""

        return f"{manifest.skill_name}: 优先级更低或来源层级靠后。"

    def _contract_summary(self, manifest: SkillManifest) -> list[str]:
        """整理选中 skill 的输入输出契约摘要"""

        summary: list[str] = []
        if manifest.input_contract:
            summary.append(f"输入: {', '.join(manifest.input_contract[:3])}")
        if manifest.output_contract:
            summary.append(f"输出: {', '.join(manifest.output_contract[:3])}")
        if manifest.tool_allowlist:
            summary.append(f"工具: {', '.join(manifest.tool_allowlist[:3])}")
        return summary
