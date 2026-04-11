"""Skill 相关模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SkillManifest(BaseModel):
    """表示一个 skill 的注册清单和执行契约。"""

    skill_name: str
    source_layer: str
    visibility: str
    allowed_tags: list[str] = Field(default_factory=list)
    input_schema: str | None = None
    output_schema: str | None = None
    entry_kind: str = "placeholder"
    stage_name: str
    description: str = ""
    enabled: bool = False
    manifest_path: str | None = None


class SkillRouteDecision(BaseModel):
    """表示某一阶段的 skill 选择结果。"""

    stage_name: str
    candidate_skills: list[str] = Field(default_factory=list)
    selected_skill: str | None = None
    selection_reason: str = ""
    fallback_used: bool = False
    route_source: str | None = None

