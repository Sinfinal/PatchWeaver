"""Safety guard for LLM-generated Agent task plans."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from patchweaver.agent.actions import AgentActionName
from patchweaver.agent.planning_contracts import TaskPlan, allowed_tool_action_names
from patchweaver.agent.state import AgentObservation, sanitize_agent_payload


class PolicyGuardResult(BaseModel):
    """Result of validating one Planner-produced task plan."""

    allowed: bool
    reject_reason: str | None = None
    terminal: bool = False
    selected_action: AgentActionName | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _sanitize_fields(self) -> "PolicyGuardResult":
        self.evidence_refs = sanitize_agent_payload(self.evidence_refs)
        self.details = sanitize_agent_payload(self.details)
        return self


class PolicyGuard:
    """Validate LLM Planner output without generating the plan itself."""

    PLAN_ONLY_ACTIONS = frozenset(
        {
            AgentActionName.ANALYZE_SOURCE,
            AgentActionName.RUN_ATTEMPT,
            AgentActionName.REPORT,
            AgentActionName.REPLAY,
            AgentActionName.RETRY_WITH_STRATEGY,
        }
    )
    ATTEMPT_CONSUMING_ACTIONS = frozenset(
        {
            AgentActionName.RUN_ATTEMPT,
            AgentActionName.RUN_TASK,
            AgentActionName.RETRY_WITH_STRATEGY,
        }
    )
    TERMINAL_FAILURE_TYPES = frozenset(
        {
            "source_unavailable",
            "build_env_missing",
            "kernel_src_missing",
            "kernel_config_missing",
            "vmlinux_missing",
            "build_cache_incomplete",
        }
    )

    def validate_plan(self, plan: TaskPlan, observation: AgentObservation) -> PolicyGuardResult:
        """Return whether a Planner task plan is safe to execute."""

        action = self._normalize_action(getattr(plan, "selected_action", None))
        if action is None:
            return self._reject("非法 action：不在 AgentActionRegistry/Planner 白名单中", terminal=True)

        if action not in self._allowed_planner_actions():
            return self._reject(
                f"非法 action：{action.value} 不在 AgentActionRegistry/Planner 白名单中",
                terminal=True,
                action=action,
            )

        if action in self.ATTEMPT_CONSUMING_ACTIONS and observation.current_attempt >= observation.max_attempts:
            return self._reject(
                "重试预算已耗尽，禁止继续消耗 attempt",
                terminal=True,
                action=action,
                details={"current_attempt": observation.current_attempt, "max_attempts": observation.max_attempts},
            )

        if (
            action in self.ATTEMPT_CONSUMING_ACTIONS
            and observation.failure_type in self.TERMINAL_FAILURE_TYPES
        ):
            return self._reject(
                f"{observation.failure_type} 属于终止型失败，禁止继续消耗 attempt",
                terminal=True,
                action=action,
                details={"failure_type": observation.failure_type},
            )

        ineffective_hint = self._matching_ineffective_retry(plan, observation)
        if action == AgentActionName.RETRY_WITH_STRATEGY and ineffective_hint is not None:
            return self._reject(
                "上一轮相同策略已标记 ineffective_retry，禁止计入有效重试",
                terminal=False,
                action=action,
                details={"ineffective_retry": ineffective_hint},
            )

        if plan.risk == "high" and not plan.evidence_refs:
            return self._reject(
                "高风险动作缺少 evidence_refs，禁止执行",
                terminal=False,
                action=action,
            )

        return PolicyGuardResult(
            allowed=True,
            selected_action=action,
            evidence_refs=list(plan.evidence_refs),
            details={"guard": "agent_policy_guard"},
        )

    def _allowed_planner_actions(self) -> frozenset[AgentActionName]:
        return allowed_tool_action_names() | self.PLAN_ONLY_ACTIONS

    def _normalize_action(self, value: Any) -> AgentActionName | None:
        if isinstance(value, AgentActionName):
            return value
        try:
            return AgentActionName(str(value))
        except ValueError:
            return None

    def _matching_ineffective_retry(self, plan: TaskPlan, observation: AgentObservation) -> dict[str, Any] | None:
        planned_strategies = self._planned_strategy_names(plan)
        for hint in observation.memory_hints:
            if not isinstance(hint, dict):
                continue
            if not self._is_ineffective_hint(hint):
                continue
            hint_strategies = self._hint_strategy_names(hint)
            if not hint_strategies or planned_strategies.intersection(hint_strategies):
                return hint
        return None

    def _is_ineffective_hint(self, hint: dict[str, Any]) -> bool:
        for key in ("status", "failure_type", "outcome", "kind", "reason"):
            value = hint.get(key)
            if isinstance(value, str) and "ineffective_retry" in value:
                return True
        return False

    def _planned_strategy_names(self, plan: TaskPlan) -> set[str]:
        names: set[str] = set()
        names.update(self._strings_from(plan.budget))
        names.update(str(item) for item in plan.used_reflections)
        names.update(str(item) for item in plan.alternatives)
        names.add(plan.reason_summary)
        names.add(plan.terminal_condition)
        return {name for item in names for name in self._split_strategy_text(item)}

    def _hint_strategy_names(self, hint: dict[str, Any]) -> set[str]:
        names: set[str] = set()
        for key in ("strategy", "selected_strategy", "recipe", "selected_recipe", "route_name"):
            value = hint.get(key)
            if isinstance(value, str) and value:
                names.add(value)
        names.update(self._strings_from(hint.get("disabled_strategies")))
        names.update(self._strings_from(hint.get("strategy_requirements")))
        return {name for item in names for name in self._split_strategy_text(item)}

    def _strings_from(self, value: Any) -> set[str]:
        if isinstance(value, str):
            return {value}
        if isinstance(value, dict):
            return {item for nested in value.values() for item in self._strings_from(nested)}
        if isinstance(value, (list, tuple, set)):
            return {item for nested in value for item in self._strings_from(nested)}
        return set()

    def _split_strategy_text(self, value: str) -> set[str]:
        separators = ["+", ",", "，", " ", "\n", "\t"]
        chunks = {value.strip()}
        for separator in separators:
            next_chunks: set[str] = set()
            for chunk in chunks:
                next_chunks.update(part.strip() for part in chunk.split(separator) if part.strip())
            chunks = next_chunks
        return chunks

    def _reject(
        self,
        reason: str,
        *,
        terminal: bool,
        action: AgentActionName | None = None,
        details: dict[str, Any] | None = None,
    ) -> PolicyGuardResult:
        return PolicyGuardResult(
            allowed=False,
            reject_reason=reason,
            terminal=terminal,
            selected_action=action,
            details=details or {},
        )
