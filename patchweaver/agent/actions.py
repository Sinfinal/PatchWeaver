"""Agent action contracts."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AgentActionName(str, Enum):
    """Names of actions the Agent policy can request."""

    GET_TASK_DETAIL = "get_task_detail"
    ANALYZE_SOURCE = "analyze_source"
    ANALYZE_TASK = "analyze_task"
    RUN_ATTEMPT = "run_attempt"
    RUN_TASK = "run_task"
    REPORT = "report"
    REPORT_TASK = "report_task"
    REPLAY = "replay"
    REPLAY_TASK = "replay_task"
    RETRY_WITH_STRATEGY = "retry_with_strategy"
    REPAIR_BUILD_SOURCE_TREE = "repair_build_source_tree"
    STOP_MANUAL_REVIEW = "stop_manual_review"


class AgentAction(BaseModel):
    """Executable action requested by an Agent decision."""

    name: AgentActionName
    strategy: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
