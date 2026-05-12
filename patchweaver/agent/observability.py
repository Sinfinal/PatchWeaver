"""Optional Agent observability sinks.

The task-local ``agent_workflow_trace.json`` remains the source of truth. These
sinks are best-effort mirrors for local debugging or external observability.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from patchweaver.agent.state import (
    AgentDecision,
    AgentObservation,
    StateReduction,
    sanitize_agent_payload,
)
from patchweaver.models.task import TaskContext

_SINK_ENV = "PATCHWEAVER_OBSERVABILITY_SINK"
_LANGSMITH_TRACING_ENV = "LANGSMITH_TRACING"
_LANGSMITH_PROJECT_ENV = "LANGSMITH_PROJECT"
_DEFAULT_LANGSMITH_PROJECT = "patchweaver-dev"
_MAX_STRING_LENGTH = 800
_SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd|credential)\s*[:=]\s*['\"]?[^'\"\s,;]+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+"),
)


class ObservabilityEvent(BaseModel):
    """Sanitized Agent workflow event safe to mirror outside the main trace."""

    event_type: str = "agent_workflow_edge"
    task_id: str
    cve_id: str
    target_kernel: str
    status: str
    action_name: str
    failure_type: str | None = None
    stage: str | None = None
    terminal: bool = False
    retry: bool = False
    remaining_attempts: int | None = None
    trace_path: str | None = None
    emitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = Field(default_factory=dict)


class ObservabilitySink(Protocol):
    """Best-effort sink for sanitized Agent observability events."""

    def emit(self, event: ObservabilityEvent) -> None:
        """Emit one event without participating in task success semantics."""


class OffObservabilitySink:
    """No-op sink used when observability is disabled."""

    def emit(self, event: ObservabilityEvent) -> None:
        return None


class LocalObservabilitySink:
    """Append sanitized observability events to a task-local JSONL file."""

    def __init__(self, output_path: Path) -> None:
        self.output_path = output_path

    def emit(self, event: ObservabilityEvent) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with self.output_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n")


class LangSmithObservabilitySink:
    """Optional LangSmith sink for Agent decision telemetry only."""

    def __init__(self, *, client: Any | None = None, project_name: str | None = None) -> None:
        self.client = client if client is not None else self._load_client()
        self.project_name = project_name or os.getenv(_LANGSMITH_PROJECT_ENV) or _DEFAULT_LANGSMITH_PROJECT

    def emit(self, event: ObservabilityEvent) -> None:
        if self.client is None:
            return None
        run_payload = event.model_dump(mode="json")
        inputs = {
            "task_id": event.task_id,
            "cve_id": event.cve_id,
            "target_kernel": event.target_kernel,
            "failure_type": event.failure_type,
            "stage": event.stage,
        }
        outputs = {
            "status": event.status,
            "action_name": event.action_name,
            "terminal": event.terminal,
            "retry": event.retry,
            "remaining_attempts": event.remaining_attempts,
        }
        self.client.create_run(
            name=f"patchweaver.agent.{event.action_name}",
            run_type="chain",
            project_name=self.project_name,
            inputs=inputs,
            outputs=outputs,
            extra={"metadata": run_payload},
        )

    @staticmethod
    def _load_client() -> Any | None:
        try:
            from langsmith import Client

            return Client()
        except Exception:
            return None


def build_observability_event(
    *,
    task_id: str,
    cve_id: str,
    target_kernel: str,
    observation: AgentObservation,
    decision: AgentDecision,
    reduction: StateReduction,
    trace_path: str | None = None,
) -> ObservabilityEvent:
    """Build the sanitized event shared by all sinks."""

    action_name = _enum_value(decision.selected_action)
    payload = redact_observability_payload(
        {
            "observation": observation.model_dump(mode="json"),
            "decision": decision.model_dump(mode="json"),
            "state_reduction": reduction.model_dump(mode="json"),
        }
    )
    return ObservabilityEvent(
        task_id=task_id,
        cve_id=cve_id,
        target_kernel=target_kernel,
        status=reduction.next_stage,
        action_name=action_name,
        failure_type=observation.failure_type,
        stage=observation.stage or observation.latest_status or observation.task_status,
        terminal=reduction.terminal,
        retry=decision.retry,
        remaining_attempts=reduction.remaining_attempts,
        trace_path=trace_path,
        payload=payload,
    )


def build_langgraph_observability_event(
    *,
    node: str,
    step_index: int,
    status: str,
    payload: dict[str, Any],
    task: TaskContext | None = None,
    task_id: str | None = None,
    cve_id: str | None = None,
    target_kernel: str | None = None,
    trace_path: str | None = None,
) -> ObservabilityEvent:
    """Build one sanitized LangGraph node event for optional mirrors.

    This mirrors only structured node summaries. The task workspace trace remains
    the source of truth and raw logs are intentionally excluded.
    """

    effective_task_id = task.task_id if task is not None else task_id
    effective_cve_id = task.cve_id if task is not None else cve_id
    effective_target_kernel = task.target_kernel if task is not None else target_kernel
    if not effective_task_id or not effective_cve_id or not effective_target_kernel:
        raise ValueError("LangGraph observability event requires task_id, cve_id and target_kernel")

    clean_payload = redact_observability_payload(
        {
            "node": node,
            "step_index": step_index,
            "status": status,
            "payload": payload,
        }
    )
    return ObservabilityEvent(
        event_type="agent_langgraph_node",
        task_id=effective_task_id,
        cve_id=effective_cve_id,
        target_kernel=effective_target_kernel,
        status=status,
        action_name=_langgraph_action_name(node=node, payload=clean_payload),
        failure_type=_langgraph_failure_type(clean_payload),
        stage=node,
        terminal=_langgraph_terminal(clean_payload),
        retry=_langgraph_retry(clean_payload),
        remaining_attempts=_langgraph_remaining_attempts(clean_payload),
        trace_path=trace_path,
        payload=clean_payload,
    )


def emit_observability_event(
    *,
    event: ObservabilityEvent,
    sink: ObservabilitySink | None = None,
    workspace_dir: Path | None = None,
    environ: dict[str, str] | None = None,
) -> None:
    """Best-effort event emission that never changes task state."""

    try:
        selected_sink = sink or build_observability_sink(workspace_dir=workspace_dir, environ=environ)
        selected_sink.emit(event)
    except Exception:
        return None


def build_observability_sink(
    *,
    workspace_dir: Path | None = None,
    environ: dict[str, str] | None = None,
    langsmith_client: Any | None = None,
) -> ObservabilitySink:
    """Create the configured sink. Unset config defaults to off."""

    env = environ if environ is not None else os.environ
    sink_name = env.get(_SINK_ENV, "off").strip().lower()
    if sink_name == "local":
        if workspace_dir is None:
            return OffObservabilitySink()
        return LocalObservabilitySink(workspace_dir / "agent" / "agent_observability_events.jsonl")
    if sink_name == "langsmith":
        tracing_enabled = env.get(_LANGSMITH_TRACING_ENV, "").strip().lower() in {"1", "true", "yes", "on"}
        if not tracing_enabled:
            return OffObservabilitySink()
        return LangSmithObservabilitySink(
            client=langsmith_client,
            project_name=env.get(_LANGSMITH_PROJECT_ENV) or _DEFAULT_LANGSMITH_PROJECT,
        )
    return OffObservabilitySink()


def redact_observability_payload(value: Any) -> Any:
    """Apply secret-key redaction plus value scrubbing and log-size limits."""

    sanitized = sanitize_agent_payload(value)
    return _scrub_values(sanitized)


def _scrub_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _scrub_values(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub_values(item) for item in value]
    if isinstance(value, tuple):
        return [_scrub_values(item) for item in value]
    if isinstance(value, str):
        scrubbed = value
        for pattern in _SENSITIVE_VALUE_PATTERNS:
            scrubbed = pattern.sub("[REDACTED]", scrubbed)
        if len(scrubbed) > _MAX_STRING_LENGTH:
            return scrubbed[:_MAX_STRING_LENGTH] + "...[TRUNCATED]"
        return scrubbed
    return value


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _langgraph_action_name(*, node: str, payload: dict[str, Any]) -> str:
    raw_payload = payload.get("payload") if isinstance(payload, dict) else {}
    if not isinstance(raw_payload, dict):
        return node
    for container_name in ("plan", "tool_result", "guard", "reflection", "route"):
        container = raw_payload.get(container_name)
        if not isinstance(container, dict):
            continue
        for key in ("selected_action", "action_name", "executable_action"):
            value = container.get(key)
            if value:
                return _enum_value(value)
    return node


def _langgraph_failure_type(payload: dict[str, Any]) -> str | None:
    raw_payload = payload.get("payload") if isinstance(payload, dict) else {}
    if not isinstance(raw_payload, dict):
        return None
    for container_name in ("observation", "reflection", "reduction"):
        container = raw_payload.get(container_name)
        if isinstance(container, dict):
            value = container.get("failure_type")
            if value:
                return str(value)
    return None


def _langgraph_terminal(payload: dict[str, Any]) -> bool:
    raw_payload = payload.get("payload") if isinstance(payload, dict) else {}
    if not isinstance(raw_payload, dict):
        return False
    for container_name in ("guard", "tool_result", "reflection", "reduction", "route"):
        container = raw_payload.get(container_name)
        if isinstance(container, dict) and bool(container.get("terminal")):
            return True
    return False


def _langgraph_retry(payload: dict[str, Any]) -> bool:
    raw_payload = payload.get("payload") if isinstance(payload, dict) else {}
    if not isinstance(raw_payload, dict):
        return False
    plan = raw_payload.get("plan")
    if isinstance(plan, dict) and plan.get("selected_action") == "retry_with_strategy":
        return True
    return _langgraph_action_name(node="", payload=payload) == "retry_with_strategy"


def _langgraph_remaining_attempts(payload: dict[str, Any]) -> int | None:
    raw_payload = payload.get("payload") if isinstance(payload, dict) else {}
    if not isinstance(raw_payload, dict):
        return None
    for container_name in ("plan", "reduction"):
        container = raw_payload.get(container_name)
        if not isinstance(container, dict):
            continue
        budget = container.get("budget")
        if isinstance(budget, dict):
            value = budget.get("remaining_attempts")
            if isinstance(value, int):
                return value
        value = container.get("remaining_attempts")
        if isinstance(value, int):
            return value
    return None
