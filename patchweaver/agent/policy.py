"""Agent decision policy."""

from __future__ import annotations

from typing import Any

from patchweaver.agent.actions import AgentAction, AgentActionName
from patchweaver.agent.state import AgentDecision, AgentObservation


class DecisionPolicy:
    """Map normalized observations to bounded Agent decisions."""

    def decide(self, observation: AgentObservation) -> AgentDecision:
        """Return the next workflow decision for one observation."""

        if observation.latest_status in {"built", "target_state"}:
            return self._terminal(
                observation,
                action=AgentActionName.REPORT,
                reason="当前状态已到终止态，进入报告与回放",
                risk="low",
            )

        failure_type = observation.failure_type or "unknown"
        if failure_type == "source_unavailable":
            return self._terminal(
                observation,
                reason="source_unavailable 说明没有解析到可下载修复提交，需补来源映射或更换有明确修复提交的 CVE",
                risk="manual",
            )
        if failure_type == "target_already_patched":
            return self._terminal(
                observation,
                reason="target_already_patched 说明目标源码已包含修复，需切换未修复 stable source 基线",
                risk="manual",
            )
        if failure_type == "build_cache_incomplete":
            return self._terminal(
                observation,
                reason="build_cache_incomplete 需要先修复 Module.symvers、vmlinux 或源码构建缓存",
                risk="environment",
            )
        if failure_type == "build_env_missing":
            repair_count = int(self._diagnostic_path(observation, "repair_build_source_tree_count") or 0)
            if repair_count < 1:
                return AgentDecision(
                    selected_action=AgentActionName.REPAIR_BUILD_SOURCE_TREE,
                    reason="build_env_missing：源码树只读，自动尝试创建 attempt 级可写构建树后重试（最多1次）",
                    evidence_refs=list(observation.evidence_refs),
                    risk="low",  # type: ignore[arg-type]
                    terminal=False,
                    retry=False,
                    action=AgentAction(name=AgentActionName.REPAIR_BUILD_SOURCE_TREE),
                )
            return self._terminal(
                observation,
                reason="build_env_missing：可写构建树修复已尝试1次仍失败，需人工检查磁盘空间或 Docker 挂载配置",
                risk="environment",
            )
        if failure_type == "dependency_gap":
            return self._retry(
                observation,
                reason="dependency_gap 说明 modpost 存在未解析依赖符号，需要补齐依赖模块构建目标后重试",
                risk="medium",
                strategy_requirements=["expand_module_dependencies", "dependency_target_inference", "build_target_retry"],
            )
        if failure_type == "patch_apply_failed":
            return self._patch_apply_decision(observation)
        if failure_type == "ineffective_retry" or self._route_effectiveness_status(observation) == "ineffective_retry":
            disabled = self._previous_strategy_names(observation)
            return self._retry(
                observation,
                reason="上一轮 patch 形态无有效变化，本轮不计入有效优化并禁用上一轮策略",
                risk="medium",
                strategy_requirements=["select_distinct_recipe", "patch_shape_must_change"],
                disabled_strategies=disabled,
            )
        if failure_type in {
            "kpatch_constraint",
            "kpatch_symbol_bundle_constraint",
            "kpatch_section_symbol_offset_constraint",
        }:
            return self._retry(
                observation,
                reason="kpatch 后端约束允许切换改写策略继续尝试",
                risk="medium",
                strategy_requirements=[
                    "alternative_recipe",
                    "section_change_avoidance",
                    "semantic_guard_rewrite",
                    "smpl_primary",
                ],
            )

        return self._terminal(
            observation,
            reason=f"{failure_type} 暂无安全自动重试策略，转入人工复核",
            risk="manual",
        )

    def _patch_apply_decision(self, observation: AgentObservation) -> AgentDecision:
        subtype = self._diagnostic_path(observation, "patch_apply", "subtype") or "unknown"
        if subtype in {"context_mismatch", "source_too_new_or_already_patched"}:
            requirements = ["stable_source_baseline", "reverse_unpatch", "context_adapter"]
            reason = "patch_apply_failed/context_mismatch 需要先切未修复 stable source 基线或执行源码状态对齐"
        elif subtype == "missing_file":
            requirements = ["stable_source_baseline", "source_tree_mapping"]
            reason = "patch_apply_failed/missing_file 需要先确认目标源码树和受影响文件映射"
        else:
            requirements = ["stable_source_baseline", "apply_precheck_repair"]
            reason = "patch_apply_failed 需要按子类型执行源码状态对齐后再重试"
        return self._retry(
            observation,
            reason=reason,
            risk="medium",
            strategy_requirements=requirements,
        )

    def _terminal(
        self,
        observation: AgentObservation,
        *,
        reason: str,
        risk: str,
        action: AgentActionName = AgentActionName.STOP_MANUAL_REVIEW,
    ) -> AgentDecision:
        return AgentDecision(
            selected_action=action,
            reason=reason,
            evidence_refs=list(observation.evidence_refs),
            risk=risk,  # type: ignore[arg-type]
            terminal=True,
            retry=False,
            action=AgentAction(name=action),
        )

    def _retry(
        self,
        observation: AgentObservation,
        *,
        reason: str,
        risk: str,
        strategy_requirements: list[str],
        disabled_strategies: list[str] | None = None,
    ) -> AgentDecision:
        next_attempt = int(observation.latest_attempt_no or observation.current_attempt or 0) + 1
        return AgentDecision(
            selected_action=AgentActionName.RETRY_WITH_STRATEGY,
            reason=reason,
            evidence_refs=list(observation.evidence_refs),
            risk=risk,  # type: ignore[arg-type]
            terminal=False,
            retry=True,
            strategy_requirements=strategy_requirements,
            disabled_strategies=disabled_strategies or [],
            next_attempt_no=next_attempt,
            action=AgentAction(
                name=AgentActionName.RETRY_WITH_STRATEGY,
                strategy="+".join(strategy_requirements),
                parameters={"requirements": strategy_requirements},
            ),
        )

    def _diagnostic_path(self, observation: AgentObservation, *path: str) -> Any:
        value: Any = observation.diagnostics
        for part in path:
            if not isinstance(value, dict):
                return None
            value = value.get(part)
        return value

    def _route_effectiveness_status(self, observation: AgentObservation) -> str | None:
        value = self._diagnostic_path(observation, "route_effectiveness", "status")
        return value if isinstance(value, str) else None

    def _previous_strategy_names(self, observation: AgentObservation) -> list[str]:
        names: list[str] = []
        for key in ("selected_recipe", "recipe", "route_name", "strategy"):
            value = self._diagnostic_path(observation, "route_effectiveness", key)
            if isinstance(value, str) and value:
                names.append(value)
        return list(dict.fromkeys(names))
