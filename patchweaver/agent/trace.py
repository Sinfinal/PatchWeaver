"""Agent workflow trace writer."""

from __future__ import annotations

import json
from pathlib import Path

from patchweaver.agent.observability import build_observability_event, emit_observability_event
from patchweaver.agent.state import AgentDecision, AgentObservation, StateReduction, sanitize_agent_payload
from patchweaver.models.task import TaskContext
from patchweaver.utils.path_policy import to_project_relative


def append_agent_workflow_trace(
    *,
    task: TaskContext,
    observation: AgentObservation,
    decision: AgentDecision,
    reduction: StateReduction,
    project_root: Path | None = None,
) -> Path:
    """Append one Agent observation/decision edge to a task-local trace."""

    trace_path = task.workspace_dir / "agent" / "agent_workflow_trace.json"
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    if trace_path.exists():
        try:
            payload = json.loads(trace_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
    else:
        payload = {}

    payload.setdefault("task_id", task.task_id)
    payload.setdefault("cve_id", task.cve_id)
    payload.setdefault("target_kernel", task.target_kernel)
    payload.setdefault("observations", [])
    payload.setdefault("decisions", [])
    payload.setdefault("state_reductions", [])
    payload["trace_path"] = to_project_relative(project_root, trace_path)
    payload["observations"].append(observation.model_dump(mode="json"))
    payload["decisions"].append(decision.model_dump(mode="json"))
    payload["state_reductions"].append(reduction.model_dump(mode="json"))

    trace_path.write_text(
        json.dumps(sanitize_agent_payload(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    event = build_observability_event(
        task_id=task.task_id,
        cve_id=task.cve_id,
        target_kernel=task.target_kernel,
        observation=observation,
        decision=decision,
        reduction=reduction,
        trace_path=payload["trace_path"],
    )
    emit_observability_event(event=event, workspace_dir=task.workspace_dir)
    return trace_path
