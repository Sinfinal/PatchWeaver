"""Optional LangGraph adapter feasibility gate.

This module deliberately does not run PatchWeaver business stages. It only checks
whether the current Agent state contracts can be represented as a durable graph.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from patchweaver.agent.state import AgentState, reduce_observation, sanitize_agent_payload


class LangGraphPocResult(BaseModel):
    """Result of evaluating the optional LangGraph adapter gate."""

    langgraph_available: bool
    adoption_decision: str
    constraints: dict[str, bool] = Field(default_factory=dict)
    workflow_trace: dict[str, Any] = Field(default_factory=dict)
    checkpoint_path: str | None = None


def evaluate_langgraph_poc(*, state: AgentState, checkpoint_path: Path | None = None) -> LangGraphPocResult:
    """Evaluate whether current Agent contracts are ready for a LangGraph adapter."""

    langgraph_available = importlib.util.find_spec("langgraph") is not None
    workflow_trace = _workflow_trace_from_state(state)
    constraints = {
        "does_not_introduce_second_success_judgement": True,
        "does_not_rewrite_task_runner": True,
        "does_not_rewrite_harness": True,
        "does_not_execute_shell": True,
        "uses_guarded_action_contract": True,
        "trace_shape_matches_agent_trace": bool(workflow_trace.get("selected_action")),
    }
    adoption_decision = (
        "ready_for_optional_adapter"
        if langgraph_available and all(constraints.values())
        else "defer_until_dependency_available"
    )
    result = LangGraphPocResult(
        langgraph_available=langgraph_available,
        adoption_decision=adoption_decision,
        constraints=constraints,
        workflow_trace=workflow_trace,
        checkpoint_path=str(checkpoint_path) if checkpoint_path is not None else None,
    )
    if checkpoint_path is not None:
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_path.write_text(
            json.dumps(
                sanitize_agent_payload(
                    {
                        "state": state.model_dump(mode="json"),
                        "result": result.model_dump(mode="json"),
                        "workflow_trace": workflow_trace,
                    }
                ),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return result


def recover_langgraph_poc_checkpoint(checkpoint_path: Path) -> dict[str, Any]:
    """Recover a previously written PoC checkpoint without invoking business stages."""

    payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _workflow_trace_from_state(state: AgentState) -> dict[str, Any]:
    latest_observation = state.observations[-1] if state.observations else None
    latest_decision = state.decisions[-1] if state.decisions else None
    reduction = (
        reduce_observation(latest_observation, latest_decision)
        if latest_observation is not None and latest_decision is not None
        else None
    )
    return sanitize_agent_payload(
        {
            "task_id": state.task_id,
            "nodes": ["observe", "decide", "guarded_action", "reduce"],
            "current_stage": state.stage,
            "selected_action": latest_decision.selected_action.value if latest_decision is not None else None,
            "terminal": latest_decision.terminal if latest_decision is not None else False,
            "next_stage": reduction.next_stage if reduction is not None else None,
            "remaining_attempts": reduction.remaining_attempts if reduction is not None else None,
            "state_schema": "AgentState",
            "observation_schema": "AgentObservation",
            "decision_schema": "AgentDecision",
            "reducer_schema": "StateReduction",
        }
    )
