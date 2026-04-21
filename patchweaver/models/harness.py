"""Harness 运行模型"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from patchweaver.models.skill import SkillRouteDecision


def _utc_now() -> datetime:
    """返回当前 UTC 时间"""

    return datetime.now(timezone.utc)


class StateTransition(BaseModel):
    """表示一次状态迁移记录"""

    from_stage: str
    to_stage: str
    reason: str


class ToolCallRecord(BaseModel):
    """表示一次工具调用记录"""

    tool_name: str
    action: str
    status: str
    detail: str = ""


class SubagentRecord(BaseModel):
    """表示一条受限子代理调用记录"""

    name: str
    task_scope: str
    readonly: bool = True
    summary: str = ""


class ArtifactRef(BaseModel):
    """表示一份归档产物的索引信息"""

    artifact_type: str
    artifact_path: Path
    summary: str = ""


class HarnessTrace(BaseModel):
    """表示单轮执行的状态迁移和工具轨迹"""

    trace_id: str
    task_id: str
    attempt_no: int
    state_transitions: list[StateTransition] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    skill_route: SkillRouteDecision | None = None
    subagent_records: list[SubagentRecord] = Field(default_factory=list)
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)
    extras: dict[str, Any] = Field(default_factory=dict)

