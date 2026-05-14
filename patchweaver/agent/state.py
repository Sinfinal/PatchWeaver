"""Lightweight Agent state contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from patchweaver.agent.actions import AgentAction, AgentActionName
from patchweaver.models.attempt import AttemptRecord, FailureRecord
from patchweaver.models.task import TaskContext
from patchweaver.models.validation import ValidationReport

RiskLevel = Literal["low", "medium", "high", "environment", "manual"]

_SECRET_KEY_PARTS = ("api_key", "apikey", "secret", "token", "password", "passwd", "credential")


def sanitize_agent_payload(value: Any) -> Any:
    """Remove secret-looking fields from values stored in Agent traces."""

    if isinstance(value, BaseModel):
        return sanitize_agent_payload(value.model_dump(mode="json"))
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            if any(part in lowered for part in _SECRET_KEY_PARTS):
                sanitized[key_text] = "[REDACTED]"
                continue
            sanitized[key_text] = sanitize_agent_payload(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_agent_payload(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_agent_payload(item) for item in value]
    return value


class AgentObservation(BaseModel):
    """Normalized task observation consumed by the Agent policy."""

    task_id: str
    cve_id: str
    target_kernel: str
    task_status: str
    max_attempts: int
    current_attempt: int
    latest_attempt_no: int | None = None
    latest_attempt_id: str | None = None
    latest_status: str | None = None
    failure_type: str | None = None
    stage: str | None = None
    failure_summary: str | None = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    validation_status: str | None = None
    validation_results: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    memory_hints: list[dict[str, Any]] = Field(default_factory=list)

    @classmethod
    def from_runtime(
        cls,
        *,
        task: TaskContext,
        latest_attempt: AttemptRecord | None,
        failure_record: FailureRecord | None,
        validation_report: ValidationReport | None,
        memory_hints: list[dict[str, Any]] | None = None,
    ) -> "AgentObservation":
        """Build one policy-ready observation from runtime domain objects."""

        evidence_refs = list(failure_record.evidence if failure_record is not None else [])
        if latest_attempt is not None and latest_attempt.build_log_path is not None:
            evidence_refs.append(str(latest_attempt.build_log_path))

        validation_results: dict[str, Any] = {}
        validation_evidence: list[str] = []
        validation_failure_detail: str | None = None
        if validation_report is not None:
            validation_results = {
                "semantic_precheck": validation_report.semantic_precheck_result.model_dump(mode="json"),
                "load": validation_report.load_result.model_dump(mode="json"),
                "unload": validation_report.unload_result.model_dump(mode="json"),
                "smoke": validation_report.smoke_result.model_dump(mode="json"),
                "selftest": validation_report.selftest_result.model_dump(mode="json"),
                "regression": validation_report.regression_result.model_dump(mode="json"),
                "semantic_guard": validation_report.semantic_guard_result.model_dump(mode="json"),
            }
            validation_evidence = _validation_evidence_refs(validation_report)
            validation_failure_detail = _validation_failure_detail(validation_report)

        failure_type = (
            failure_record.failure_type
            if failure_record is not None
            else latest_attempt.failure_type
            if latest_attempt is not None
            else None
        )
        if failure_type in {"", "none", "None"}:
            failure_type = None
        if failure_type is None and validation_report is not None and validation_report.status == "failed":
            failure_type = "validation_failed"
        evidence_refs.extend(validation_evidence)
        return cls(
            task_id=task.task_id,
            cve_id=task.cve_id,
            target_kernel=task.target_kernel,
            task_status=task.status,
            max_attempts=max(1, int(task.max_attempts or 1)),
            current_attempt=int(task.current_attempt or 0),
            latest_attempt_no=latest_attempt.attempt_no if latest_attempt is not None else None,
            latest_attempt_id=latest_attempt.attempt_id if latest_attempt is not None else None,
            latest_status=latest_attempt.status if latest_attempt is not None else None,
            failure_type=failure_type,
            stage=failure_record.stage_name if failure_record is not None else "validation" if failure_type == "validation_failed" else None,
            failure_summary=failure_record.summary if failure_record is not None else validation_failure_detail,
            diagnostics=sanitize_agent_payload(failure_record.diagnostic_details if failure_record is not None else {}),
            validation_status=validation_report.status if validation_report is not None else None,
            validation_results=sanitize_agent_payload(validation_results),
            evidence_refs=list(dict.fromkeys(str(item) for item in evidence_refs if item)),
            memory_hints=sanitize_agent_payload(memory_hints or []),
        )


class AgentDecision(BaseModel):
    """Policy decision produced from an observation."""

    selected_action: AgentActionName
    reason: str
    evidence_refs: list[str] = Field(default_factory=list)
    risk: RiskLevel = "low"
    terminal: bool = False
    retry: bool = False
    strategy_requirements: list[str] = Field(default_factory=list)
    disabled_strategies: list[str] = Field(default_factory=list)
    next_attempt_no: int | None = None
    action: AgentAction | None = None


class AgentState(BaseModel):
    """Serializable workflow state visible to reports and Web/API."""

    task_id: str
    stage: str = "created"
    current_attempt: int = 0
    max_attempts: int = 1
    disabled_strategies: list[str] = Field(default_factory=list)
    observations: list[AgentObservation] = Field(default_factory=list)
    decisions: list[AgentDecision] = Field(default_factory=list)


class StateReduction(BaseModel):
    """Result of applying one decision to the workflow state."""

    task_id: str
    previous_stage: str | None = None
    next_stage: str
    terminal: bool
    remaining_attempts: int
    selected_action: AgentActionName
    disabled_strategies: list[str] = Field(default_factory=list)


def reduce_observation(observation: AgentObservation, decision: AgentDecision) -> StateReduction:
    """Reduce one observation and decision into the next workflow edge."""

    remaining_attempts = max(
        0,
        observation.max_attempts - int(observation.latest_attempt_no or observation.current_attempt or 0),
    )
    if decision.selected_action == AgentActionName.RETRY_WITH_STRATEGY:
        next_stage = "run_attempt"
    elif decision.selected_action == AgentActionName.ANALYZE_SOURCE:
        next_stage = "retrieval"
    elif decision.selected_action == AgentActionName.REPORT:
        next_stage = "report"
    elif decision.selected_action == AgentActionName.REPLAY:
        next_stage = "replay"
    elif decision.selected_action == AgentActionName.RUN_ATTEMPT:
        next_stage = "run_attempt"
    else:
        next_stage = "manual_review" if decision.terminal else "stopped"

    return StateReduction(
        task_id=observation.task_id,
        previous_stage=observation.stage or observation.latest_status or observation.task_status,
        next_stage=next_stage,
        terminal=decision.terminal,
        remaining_attempts=remaining_attempts,
        selected_action=decision.selected_action,
        disabled_strategies=list(decision.disabled_strategies),
    )


def _validation_evidence_refs(validation_report: ValidationReport) -> list[str]:
    refs: list[str] = []
    for item in (
        validation_report.semantic_precheck_result,
        validation_report.load_result,
        validation_report.unload_result,
        validation_report.smoke_result,
        validation_report.selftest_result,
        validation_report.regression_result,
        validation_report.semantic_guard_result,
    ):
        if item.log_path:
            refs.append(item.log_path)
    for entry in validation_report.validation_matrix:
        if entry.log_path:
            refs.append(entry.log_path)
    return list(dict.fromkeys(refs))


def _validation_failure_detail(validation_report: ValidationReport) -> str | None:
    if validation_report.status != "failed":
        return None
    for name, item in (
        ("load", validation_report.load_result),
        ("unload", validation_report.unload_result),
        ("smoke", validation_report.smoke_result),
        ("selftest", validation_report.selftest_result),
        ("semantic_guard", validation_report.semantic_guard_result),
        ("regression", validation_report.regression_result),
        ("semantic_precheck", validation_report.semantic_precheck_result),
    ):
        if item.status == "failed":
            return f"{name}: {item.detail}"
    return "validation_report status failed"
