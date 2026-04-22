"""语义卡片模型"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SemanticCard(BaseModel):
    """表示修复意图的最小语义边界"""

    bug_class: str = "unknown"
    root_cause: str = ""
    must_keep_conditions: list[str] = Field(default_factory=list)
    must_keep_side_effects: list[str] = Field(default_factory=list)
    critical_calls: list[str] = Field(default_factory=list)
    touched_files: list[str] = Field(default_factory=list)
    touched_functions: list[str] = Field(default_factory=list)


class SemanticCardEnrichmentTrace(BaseModel):
    """表示语义卡片模型补全过程的留痕信息"""

    status: Literal["applied", "skipped", "failed"] = "skipped"
    applied: bool = False
    provider: str | None = None
    model_name: str | None = None
    selected_skill: str | None = None
    prompt_packet_path: str | None = None
    source_evidence_path: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    merged_fields: list[str] = Field(default_factory=list)
    reason: str | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    draft_card: dict[str, Any] = Field(default_factory=dict)
    model_output: dict[str, Any] | None = None
    raw_response_text: str | None = None
    record_mode: Literal["off", "basic", "full"] | None = None
    interaction_record_path: str | None = None
    duration_ms: int | None = None
    context_token_cost: int = 0
    context_evidence_count: int = 0
    context_duplicate_hits: int = 0
    context_memory_hits: int = 0
