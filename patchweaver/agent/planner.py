"""LLM-backed Planner for autonomous Agent task routing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from patchweaver.agent.actions import AgentActionName
from patchweaver.agent.planning_contracts import (
    AgentGoal,
    ReflectionRecord,
    TaskPlan,
    allowed_tool_action_names,
)
from patchweaver.agent.policy import DecisionPolicy
from patchweaver.agent.state import AgentDecision, AgentObservation, sanitize_agent_payload
from patchweaver.config.models import ModelsConfig
from patchweaver.prompting.model_client import ModelClientError, OpenAICompatibleChatClient


class LLMPlanner:
    """Create a structured TaskPlan from task observations and memory."""

    PLAN_ONLY_ACTIONS = frozenset(
        {
            AgentActionName.ANALYZE_SOURCE,
            AgentActionName.RUN_ATTEMPT,
            AgentActionName.REPORT,
            AgentActionName.REPLAY,
            AgentActionName.RETRY_WITH_STRATEGY,
        }
    )

    def __init__(
        self,
        *,
        models_config: ModelsConfig | None = None,
        chat_client: OpenAICompatibleChatClient | None = None,
        fallback_policy: DecisionPolicy | None = None,
        project_root: Path | None = None,
        trace_path: Path | None = None,
        prompt_path: Path | None = None,
    ) -> None:
        self.models_config = models_config
        self.chat_client = chat_client or self._build_default_client(models_config)
        self.fallback_policy = fallback_policy or DecisionPolicy()
        self.project_root = project_root.resolve() if project_root is not None else None
        self.trace_path = trace_path or self._default_trace_path(project_root)
        self.prompt_path = prompt_path or Path(__file__).resolve().parent / "prompts" / "planner_system.md"

    def plan(
        self,
        *,
        observation: AgentObservation,
        goal: AgentGoal,
        memory_hints: list[dict[str, Any]] | None = None,
        rag_hints: list[dict[str, Any]] | None = None,
        available_actions: list[AgentActionName | str] | None = None,
        reflections: list[ReflectionRecord] | None = None,
    ) -> TaskPlan:
        """Return the next structured task plan."""

        normalized_actions = self._normalize_available_actions(available_actions)
        reflections = reflections or []
        if self.chat_client is None:
            plan = self._fallback_plan(
                observation=observation,
                goal=goal,
                reason="模型不可用，使用 DecisionPolicy fallback",
            )
            self._write_trace(
                observation=observation,
                goal=goal,
                plan=plan,
                mode="fallback_rule_plan",
                memory_hints=memory_hints or [],
                rag_hints=rag_hints or [],
                available_actions=normalized_actions,
                reflections=reflections,
            )
            return plan

        system_prompt = self._system_prompt(reflections)
        user_prompt = self._user_prompt(
            observation=observation,
            goal=goal,
            memory_hints=memory_hints or observation.memory_hints,
            rag_hints=rag_hints or [],
            available_actions=normalized_actions,
        )

        try:
            response = self.chat_client.chat_json(
                model=self._model_name(),
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.0,
            )
            plan = self._parse_plan(response.payload, available_actions=normalized_actions)
            if self._repeats_completed_analysis(plan, observation):
                plan = self._fallback_plan(
                    observation=observation,
                    goal=goal,
                    reason="模型重复选择已完成的分析动作，使用 DecisionPolicy fallback",
                )
                self._write_trace(
                    observation=observation,
                    goal=goal,
                    plan=plan,
                    mode="fallback_rule_plan",
                    memory_hints=memory_hints or [],
                    rag_hints=rag_hints or [],
                    available_actions=normalized_actions,
                    reflections=reflections,
                    error="repeated_completed_analysis",
                )
                return plan
            if self._repeats_after_validation_result(plan, observation):
                plan = self._fallback_plan(
                    observation=observation,
                    goal=goal,
                    reason="模型在已有验证结果后仍选择继续消耗 attempt，使用 DecisionPolicy fallback",
                )
                self._write_trace(
                    observation=observation,
                    goal=goal,
                    plan=plan,
                    mode="fallback_rule_plan",
                    memory_hints=memory_hints or [],
                    rag_hints=rag_hints or [],
                    available_actions=normalized_actions,
                    reflections=reflections,
                    error="attempt_consuming_after_validation_result",
                )
                return plan
        except ModelClientError as exc:
            plan = self._fallback_plan(
                observation=observation,
                goal=goal,
                reason=f"模型规划失败，使用 DecisionPolicy fallback: {exc}",
            )
            self._write_trace(
                observation=observation,
                goal=goal,
                plan=plan,
                mode="fallback_rule_plan",
                memory_hints=memory_hints or [],
                rag_hints=rag_hints or [],
                available_actions=normalized_actions,
                reflections=reflections,
                error=str(exc),
            )
            return plan
        except ValueError as exc:
            if "Planner 输出未注册 action" not in str(exc):
                raise
            plan = self._fallback_plan(
                observation=observation,
                goal=goal,
                reason=f"模型选择了当前 runtime 不开放的 action，使用 DecisionPolicy fallback: {exc}",
            )
            self._write_trace(
                observation=observation,
                goal=goal,
                plan=plan,
                mode="fallback_rule_plan",
                memory_hints=memory_hints or [],
                rag_hints=rag_hints or [],
                available_actions=normalized_actions,
                reflections=reflections,
                error=str(exc),
            )
            return plan

        self._write_trace(
            observation=observation,
            goal=goal,
            plan=plan,
            mode="llm_plan",
            memory_hints=memory_hints or [],
            rag_hints=rag_hints or [],
            available_actions=normalized_actions,
            reflections=reflections,
        )
        return plan

    def _parse_plan(self, payload: dict[str, Any], *, available_actions: list[AgentActionName]) -> TaskPlan:
        try:
            plan = TaskPlan.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(f"Planner 输出无法通过 TaskPlan schema 校验: {exc}") from exc
        if plan.selected_action not in set(available_actions):
            raise ValueError(f"Planner 输出未注册 action: {plan.selected_action.value}")
        return plan

    def _fallback_plan(self, *, observation: AgentObservation, goal: AgentGoal, reason: str) -> TaskPlan:
        artifact_state = observation.diagnostics.get("artifact_state")
        artifact_state = artifact_state if isinstance(artifact_state, dict) else {}
        if self._should_replay_after_report(observation=observation, artifact_state=artifact_state):
            return TaskPlan(
                goal_id=goal.goal_id,
                selected_action=AgentActionName.REPLAY_TASK,
                alternatives=["replay_task"],
                reason_summary=f"{reason}; 终止态报告已存在，下一步补齐 replay 证据闭环",
                evidence_refs=list(observation.evidence_refs),
                risk="manual" if observation.failure_type else "low",
                budget={
                    "plan_mode": "fallback_rule_plan",
                    "remaining_attempts": max(0, observation.max_attempts - observation.current_attempt),
                },
                terminal_condition="replay 输出后停止自动流程，等待提交或人工复核",
                used_reflections=[],
            )
        if observation.validation_status in {"passed", "failed", "partial"} or observation.latest_status == "built":
            if artifact_state.get("report_json_exists") and not artifact_state.get("replay_recorded"):
                return TaskPlan(
                    goal_id=goal.goal_id,
                    selected_action=AgentActionName.REPLAY_TASK,
                    alternatives=["replay_task"],
                    reason_summary=f"{reason}; 已有报告或验证结果，下一步补齐 replay 证据闭环",
                    evidence_refs=list(observation.evidence_refs),
                    risk="low" if observation.validation_status == "passed" else "manual",
                    budget={
                        "plan_mode": "fallback_rule_plan",
                        "remaining_attempts": max(0, observation.max_attempts - observation.current_attempt),
                    },
                    terminal_condition="replay 输出后停止自动流程，等待提交或人工复核",
                    used_reflections=[],
                )
            return TaskPlan(
                goal_id=goal.goal_id,
                selected_action=AgentActionName.REPORT_TASK,
                alternatives=["report_task", "replay_task"],
                reason_summary=f"{reason}; 当前已有构建/验证结果，应先生成 report 而不是继续消耗 attempt",
                evidence_refs=list(observation.evidence_refs),
                risk="low" if observation.validation_status == "passed" else "manual",
                budget={
                    "plan_mode": "fallback_rule_plan",
                    "remaining_attempts": max(0, observation.max_attempts - observation.current_attempt),
                },
                terminal_condition="report 生成后进入 replay 证据闭环",
                used_reflections=[],
            )

        if self._needs_source_analysis(observation):
            return TaskPlan(
                goal_id=goal.goal_id,
                selected_action=AgentActionName.ANALYZE_TASK,
                alternatives=["analyze_task", "get_task_detail"],
                reason_summary=f"{reason}; 新建任务必须先获取 CVE 来源和源码观察，不能直接消耗构建 attempt",
                evidence_refs=list(observation.evidence_refs),
                risk="low",
                budget={
                    "plan_mode": "fallback_rule_plan",
                    "remaining_attempts": max(0, observation.max_attempts - observation.current_attempt),
                },
                terminal_condition="分析后重新观察 source/patch/baseline 状态，再决定是否构建",
                used_reflections=[],
            )

        if self._looks_confirmed_positive(observation):
            return TaskPlan(
                goal_id=goal.goal_id,
                selected_action=AgentActionName.REPORT_TASK if observation.latest_status == "built" else AgentActionName.RUN_TASK,
                alternatives=["run_task", "report_task", "replay_task"],
                reason_summary=f"{reason}; 当前观察显示任务可继续 build/validate/report 主链",
                evidence_refs=list(observation.evidence_refs),
                risk="low",
                budget={
                    "plan_mode": "fallback_rule_plan",
                    "remaining_attempts": max(0, observation.max_attempts - observation.current_attempt),
                },
                terminal_condition="生成验证证据后进入 report/replay，否则按失败归因重新规划",
                used_reflections=[],
            )

        decision = self.fallback_policy.decide(observation)
        alternatives = list(decision.strategy_requirements or [])
        if decision.selected_action == AgentActionName.RETRY_WITH_STRATEGY and not alternatives:
            alternatives = ["alternative_recipe"]
        return TaskPlan(
            goal_id=goal.goal_id,
            selected_action=decision.selected_action,
            alternatives=alternatives or [decision.selected_action.value],
            reason_summary=decision.reason,
            evidence_refs=list(decision.evidence_refs),
            risk=decision.risk,
            budget={
                "plan_mode": "fallback_rule_plan",
                "remaining_attempts": max(0, observation.max_attempts - observation.current_attempt),
                "next_attempt_no": decision.next_attempt_no,
                "disabled_strategies": list(decision.disabled_strategies),
            },
            terminal_condition="terminal" if decision.terminal else "执行本轮策略后重新观察构建与验证结果",
            used_reflections=[],
        )

    def _should_replay_after_report(self, *, observation: AgentObservation, artifact_state: dict[str, Any]) -> bool:
        if not artifact_state.get("report_json_exists"):
            return False
        if artifact_state.get("replay_recorded"):
            return False
        if observation.validation_status in {"passed", "failed", "partial"}:
            return True
        if observation.latest_status in {"built", "target_state"}:
            return True
        if observation.task_status in {"built", "target_state", "failed"} and observation.failure_type is not None:
            return True
        return False

    def _repeats_completed_analysis(self, plan: TaskPlan, observation: AgentObservation) -> bool:
        return (
            plan.selected_action in {AgentActionName.ANALYZE_SOURCE, AgentActionName.ANALYZE_TASK}
            and observation.task_status == "analyzed"
            and observation.failure_type is None
            and observation.latest_attempt_no is None
            and observation.current_attempt == 0
        )

    def _repeats_after_validation_result(self, plan: TaskPlan, observation: AgentObservation) -> bool:
        attempt_consuming = {
            AgentActionName.RUN_ATTEMPT,
            AgentActionName.RUN_TASK,
            AgentActionName.RETRY_WITH_STRATEGY,
        }
        return plan.selected_action in attempt_consuming and observation.validation_status in {"passed", "failed", "partial"}

    def _looks_confirmed_positive(self, observation: AgentObservation) -> bool:
        if observation.validation_status == "passed" or observation.latest_status == "built":
            return True
        if observation.failure_type is not None:
            return False
        if observation.task_status in {"running", "analyzed"}:
            return True
        return False

    def _needs_source_analysis(self, observation: AgentObservation) -> bool:
        return (
            observation.failure_type is None
            and observation.latest_attempt_no is None
            and observation.current_attempt == 0
            and observation.task_status in {"created", "pending"}
        )

    def _normalize_available_actions(self, available_actions: list[AgentActionName | str] | None) -> list[AgentActionName]:
        raw_actions = available_actions or sorted((allowed_tool_action_names() | self.PLAN_ONLY_ACTIONS), key=lambda item: item.value)
        normalized: list[AgentActionName] = []
        allowed = allowed_tool_action_names() | self.PLAN_ONLY_ACTIONS
        for item in raw_actions:
            try:
                action = item if isinstance(item, AgentActionName) else AgentActionName(str(item))
            except ValueError as exc:
                raise ValueError(f"可用 action 未注册: {item}") from exc
            if action not in allowed:
                raise ValueError(f"可用 action 不在 AgentActionRegistry/Planner 白名单: {action.value}")
            normalized.append(action)
        return list(dict.fromkeys(normalized))

    def _system_prompt(self, reflections: list[ReflectionRecord]) -> str:
        template = self.prompt_path.read_text(encoding="utf-8") if self.prompt_path.exists() else "{{REFLECTIONS}}"
        reflection_lines = []
        for index, reflection in enumerate(reflections, start=1):
            reflection_id = self._reflection_id(reflection, index)
            reflection_lines.append(
                "\n".join(
                    [
                        f"- id: {reflection_id}",
                        f"  failure_type: {reflection.failure_type}",
                        f"  what_to_avoid: {reflection.what_to_avoid}",
                        f"  next_strategy_hint: {reflection.next_strategy_hint}",
                    ]
                )
            )
        reflection_block = "\n".join(reflection_lines) if reflection_lines else "- none"
        return template.replace("{{REFLECTIONS}}", reflection_block)

    def _user_prompt(
        self,
        *,
        observation: AgentObservation,
        goal: AgentGoal,
        memory_hints: list[dict[str, Any]],
        rag_hints: list[dict[str, Any]],
        available_actions: list[AgentActionName],
    ) -> str:
        payload = {
            "goal": goal.model_dump(mode="json"),
            "observation": observation.model_dump(mode="json"),
            "memory_hints": memory_hints,
            "rag_hints": rag_hints,
            "available_actions": [action.value for action in available_actions],
            "output_contract": {
                "schema": "TaskPlan",
                "must_include_used_reflections": True,
                "must_not_select_unavailable_action": True,
            },
        }
        return json.dumps(sanitize_agent_payload(payload), ensure_ascii=False, sort_keys=True)

    def _write_trace(
        self,
        *,
        observation: AgentObservation,
        goal: AgentGoal,
        plan: TaskPlan,
        mode: str,
        memory_hints: list[dict[str, Any]],
        rag_hints: list[dict[str, Any]],
        available_actions: list[AgentActionName],
        reflections: list[ReflectionRecord],
        error: str | None = None,
    ) -> None:
        self.trace_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "mode": mode,
            "error": error,
            "goal": goal.model_dump(mode="json"),
            "observation": observation.model_dump(mode="json"),
            "memory_hints": memory_hints,
            "rag_hints": rag_hints,
            "available_actions": [action.value for action in available_actions],
            "reflections": [reflection.model_dump(mode="json") for reflection in reflections],
            "plan": plan.model_dump(mode="json"),
        }
        self.trace_path.write_text(
            json.dumps(sanitize_agent_payload(payload), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _reflection_id(self, reflection: ReflectionRecord, index: int) -> str:
        if reflection.reflection_id:
            return reflection.reflection_id
        return f"reflection-{reflection.attempt_no or index}-{reflection.failure_type}"

    def _model_name(self) -> str:
        if self.models_config is None:
            return "unknown"
        return self.models_config.development_model or self.models_config.default_model

    def _build_default_client(self, models_config: ModelsConfig | None) -> OpenAICompatibleChatClient | None:
        if models_config is None:
            return None
        if models_config.endpoint_mode != "openai_compatible":
            return None
        api_key = models_config.resolve_api_key()
        if not api_key:
            return None
        return OpenAICompatibleChatClient(base_url=models_config.base_url, api_key=api_key)

    def _default_trace_path(self, project_root: Path | None) -> Path:
        if project_root is not None:
            return project_root / "tmp" / "agent_planner_trace.json"
        return Path("tmp") / "agent_planner_trace.json"
