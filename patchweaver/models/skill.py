"""Skill 相关模型"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SkillManifest(BaseModel):
    """表示一个 skill 的注册清单和执行契约"""

    skill_name: str
    source_layer: str
    visibility: str
    preferred_rank: int = 100
    readonly: bool = True
    allow_readonly_subagent: bool = False
    allowed_tags: list[str] = Field(default_factory=list)
    input_schema: str | None = None
    output_schema: str | None = None
    input_contract: list[str] = Field(default_factory=list)
    output_contract: list[str] = Field(default_factory=list)
    evidence_tags: list[str] = Field(default_factory=list)
    tool_allowlist: list[str] = Field(default_factory=list)
    entry_kind: str = "placeholder"
    stage_name: str
    description: str = ""
    enabled: bool = False
    manifest_path: str | None = None


class SkillRouteDecision(BaseModel):
    """表示某一阶段的 skill 选择结果"""

    stage_name: str
    candidate_skills: list[str] = Field(default_factory=list)
    selected_skill: str | None = None
    rejected_skills: list[str] = Field(default_factory=list)
    selection_reason: str = ""
    readonly_subagent_allowed: bool = False
    contract_summary: list[str] = Field(default_factory=list)
    fallback_used: bool = False
    route_source: str | None = None
