"""Skill 运行时状态"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SkillRuntime(BaseModel):
    """表示一次 skill 调度时的运行时快照"""

    stage_name: str
    selected_skill: str | None = None
    readonly: bool = True
    tool_allowlist: list[str] = Field(default_factory=list)

