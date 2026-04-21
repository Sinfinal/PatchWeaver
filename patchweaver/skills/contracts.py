"""Skill 契约定义"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field


class SkillExecutionRequest(BaseModel):
    """表示 skill 执行请求"""

    stage_name: str
    task_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


class SkillExecutionResult(BaseModel):
    """表示 skill 执行结果"""

    ok: bool
    summary: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class SkillExecutor(Protocol):
    """约定 skill 执行器的最小接口"""

    def execute(self, request: SkillExecutionRequest) -> SkillExecutionResult:
        """执行单个 skill 请求"""

