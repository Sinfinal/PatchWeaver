"""LangGraph adapter adoption decision gate.

The assessment is intentionally evidence-only. It does not replace the Harness
or TaskRunner, execute shell commands, or decide PatchWeaver task success.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

Decision = Literal["adopt_now", "defer", "reject"]
RiskSeverity = Literal["medium", "high"]


class LangGraphAdapterRisk(BaseModel):
    """Risk tracked by the LangGraph adapter decision gate."""

    name: str
    severity: RiskSeverity
    mitigation: str


class CheckpointResumeEvidence(BaseModel):
    """Evidence from a simulated long-running Agent orchestration."""

    scenario: str
    checkpoint_after_node: str
    resumed_from_checkpoint: bool
    skipped_after_resume: list[str] = Field(default_factory=list)
    completed_after_resume: list[str] = Field(default_factory=list)
    shell_executed: bool
    side_effects_replayed: bool
    benefit: str


class LangGraphAdapterAssessment(BaseModel):
    """Structured adoption decision for the optional LangGraph adapter."""

    artifact_name: str = "langgraph_adapter_assessment.json"
    decision: Decision
    rationale: str
    migrate_nodes: list[str] = Field(default_factory=list)
    do_not_migrate_nodes: list[str] = Field(default_factory=list)
    constraints: dict[str, bool] = Field(default_factory=dict)
    risks: list[LangGraphAdapterRisk] = Field(default_factory=list)
    checkpoint_resume_evidence: CheckpointResumeEvidence


def build_langgraph_adapter_assessment(*, output_path: Path | None = None) -> LangGraphAdapterAssessment:
    """Build and optionally write the LangGraph adapter decision artifact."""

    assessment = LangGraphAdapterAssessment(
        decision="defer",
        rationale=(
            "LangGraph should remain an optional adapter until AgentState, AgentAction, "
            "Observation, and Reducer contracts are stable across more successful runs."
        ),
        migrate_nodes=[
            "observe",
            "decide",
            "guarded_action_routing",
            "reduce",
            "checkpoint_resume",
        ],
        do_not_migrate_nodes=[
            "harness",
            "task_runner",
            "shell_execution",
            "success_judgement",
            "validation_truth_source",
        ],
        constraints={
            "does_not_replace_harness": True,
            "does_not_replace_task_runner": True,
            "does_not_execute_shell": True,
            "does_not_introduce_second_success_judgement": True,
            "orchestrates_agent_contracts_only": True,
        },
        risks=[
            LangGraphAdapterRisk(
                name="duplicate_state_source",
                severity="high",
                mitigation="Keep AgentState as the serialized contract and treat graph state as a projection.",
            ),
            LangGraphAdapterRisk(
                name="side_effect_replay",
                severity="high",
                mitigation="Checkpoint only pure orchestration nodes; route external work through TaskRunner once.",
            ),
            LangGraphAdapterRisk(
                name="debugging_complexity",
                severity="medium",
                mitigation="Persist node names, decisions, reductions, and evidence refs in existing traces.",
            ),
        ],
        checkpoint_resume_evidence=_simulate_long_task_checkpoint_resume(),
    )
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(assessment.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return assessment


def _simulate_long_task_checkpoint_resume() -> CheckpointResumeEvidence:
    """Simulate interruption after decision and resume without replaying side effects."""

    completed_before_interrupt = ["observe", "decide"]
    checkpoint = {
        "task_id": "TASK-LANGGRAPH-ASSESSMENT",
        "completed_nodes": completed_before_interrupt,
        "next_nodes": ["reduce", "persist_trace"],
    }
    resumed_nodes = list(checkpoint["next_nodes"])
    return CheckpointResumeEvidence(
        scenario="simulated_long_retry_task",
        checkpoint_after_node="decide",
        resumed_from_checkpoint=True,
        skipped_after_resume=list(checkpoint["completed_nodes"]),
        completed_after_resume=resumed_nodes,
        shell_executed=False,
        side_effects_replayed=False,
        benefit="resume avoids re-running observe/decide for long tasks",
    )
