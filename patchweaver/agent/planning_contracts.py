"""Structured planning contracts for the autonomous Agent loop."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from patchweaver.agent.actions import AgentActionName
from patchweaver.agent.state import RiskLevel, sanitize_agent_payload
from patchweaver.models.task import TaskContext

_SENSITIVE_KEY_PARTS = ("api_key", "apikey", "secret", "token", "password", "passwd", "credential")


def _utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


def _stable_goal_id(*, cve_id: str, target_kernel: str, task_id: str | None = None) -> str:
    """Build a stable, trace-friendly goal id."""

    raw = task_id or f"{cve_id}-{target_kernel}"
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip("-").lower()
    return f"goal-{normalized or 'patchweaver'}"


def _strip_sensitive_keys(value: Any) -> Any:
    """Drop secret-looking keys after the shared sanitizer has redacted values."""

    if isinstance(value, dict):
        stripped: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            if any(marker in lowered for marker in _SENSITIVE_KEY_PARTS):
                continue
            stripped[key_text] = _strip_sensitive_keys(item)
        return stripped
    if isinstance(value, list):
        return [_strip_sensitive_keys(item) for item in value]
    if isinstance(value, tuple):
        return [_strip_sensitive_keys(item) for item in value]
    return value


def _sanitize_contract_payload(value: Any) -> Any:
    """Apply the project-wide Agent sanitizer and remove sensitive field names."""

    return _strip_sensitive_keys(sanitize_agent_payload(value))


def allowed_tool_action_names() -> frozenset[AgentActionName]:
    """Actions registered by ``AgentActionRegistry._register_defaults``."""

    return frozenset(
        {
            AgentActionName.GET_TASK_DETAIL,
            AgentActionName.ANALYZE_TASK,
            AgentActionName.RUN_TASK,
            AgentActionName.REPORT_TASK,
            AgentActionName.REPLAY_TASK,
            AgentActionName.STOP_MANUAL_REVIEW,
        }
    )


class _SanitizedPlanningModel(BaseModel):
    """Base model that sanitizes values before they enter Agent traces."""

    @model_validator(mode="after")
    def _sanitize_fields(self) -> "_SanitizedPlanningModel":
        for field_name in self.__class__.model_fields:
            value = getattr(self, field_name)
            setattr(self, field_name, _sanitize_contract_payload(value))
        return self


class AgentGoal(_SanitizedPlanningModel):
    """Top-level objective the Planner should satisfy for one CVE task."""

    goal_id: str
    cve_id: str
    target_kernel: str
    success_conditions: list[str] = Field(default_factory=list)
    risk_boundary: list[str] = Field(default_factory=list)
    budget: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_create_request(
        cls,
        *,
        cve_id: str,
        target_kernel: str,
        max_attempts: int = 5,
        success_conditions: list[str] | None = None,
        risk_boundary: list[str] | None = None,
        budget: dict[str, Any] | None = None,
    ) -> "AgentGoal":
        """Create a goal directly from a CVE creation request."""

        return cls(
            goal_id=_stable_goal_id(cve_id=cve_id, target_kernel=target_kernel),
            cve_id=cve_id,
            target_kernel=target_kernel,
            success_conditions=success_conditions or _default_success_conditions(),
            risk_boundary=risk_boundary or _default_risk_boundary(),
            budget={"max_attempts": max(1, int(max_attempts)), **(budget or {})},
        )

    @classmethod
    def from_task_context(
        cls,
        task: TaskContext,
        *,
        success_conditions: list[str] | None = None,
        risk_boundary: list[str] | None = None,
        budget: dict[str, Any] | None = None,
    ) -> "AgentGoal":
        """Create a goal from an existing task context."""

        return cls(
            goal_id=_stable_goal_id(cve_id=task.cve_id, target_kernel=task.target_kernel, task_id=task.task_id),
            cve_id=task.cve_id,
            target_kernel=task.target_kernel,
            success_conditions=success_conditions or _default_success_conditions(),
            risk_boundary=risk_boundary or _default_risk_boundary(),
            budget={
                "max_attempts": max(1, int(task.max_attempts or 1)),
                "current_attempt": max(0, int(task.current_attempt or 0)),
                **(budget or {}),
            },
        )


class TaskPlan(_SanitizedPlanningModel):
    """Structured Planner output before PolicyGuard validation."""

    goal_id: str
    selected_action: AgentActionName
    alternatives: list[str] = Field(default_factory=list)
    reason_summary: str
    evidence_refs: list[str] = Field(default_factory=list)
    risk: RiskLevel = "low"
    budget: dict[str, Any] = Field(default_factory=dict)
    terminal_condition: str
    used_reflections: list[str] = Field(default_factory=list)


class ToolCallIntent(_SanitizedPlanningModel):
    """One guarded tool call selected from the Agent action registry."""

    action_name: AgentActionName
    task_id: str
    parameters: dict[str, Any] = Field(default_factory=dict)

    @field_validator("action_name", mode="before")
    @classmethod
    def _validate_registered_action(cls, value: AgentActionName | str) -> AgentActionName:
        try:
            action_name = value if isinstance(value, AgentActionName) else AgentActionName(str(value))
        except ValueError as exc:
            raise ValueError(f"非法 Agent tool action：{value}") from exc
        if action_name not in allowed_tool_action_names():
            raise ValueError(f"Agent action 未在 AgentActionRegistry 白名单中注册：{action_name.value}")
        return action_name


class ToolResult(_SanitizedPlanningModel):
    """Result of one guarded tool call."""

    action_name: AgentActionName
    task_id: str
    status: str
    artifact_paths: list[str] = Field(default_factory=list)
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=_utc_now)
    finished_at: datetime | None = None


class ReflectionRecord(_SanitizedPlanningModel):
    """Planner memory distilled from a failed or blocked attempt."""

    reflection_id: str | None = None
    attempt_no: int | None = None
    failure_type: str
    what_failed: str
    what_to_avoid: str
    next_strategy_hint: str
    evidence_refs: list[str] = Field(default_factory=list)
    disabled_strategies: list[str] = Field(default_factory=list)
    terminal: bool = False
    reflection_mode: str = "rule"


def _default_success_conditions() -> list[str]:
    return [
        "生成 livepatch .ko",
        "完成 load/unload/smoke/selftest",
        "输出 report/replay 证据",
    ]


def _default_risk_boundary() -> list[str]:
    return [
        "不得直接执行任意 shell",
        "不得绕过 Harness 或 TaskRunner",
        "不得在无验证证据时宣称 .ko 成功",
    ]
