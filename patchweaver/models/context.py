"""上下文装配模型"""

from __future__ import annotations

from pydantic import BaseModel, Field

from patchweaver.models.evidence import EvidenceSpan


class ContextBundle(BaseModel):
    """表示阶段执行前装配好的上下文包"""

    evidence_ids: list[str] = Field(default_factory=list)
    token_cost: int = 0
    duplicate_hits: int = 0
    memory_hits: int = 0
    memory_summaries: list[str] = Field(default_factory=list)
    source_spans: list[EvidenceSpan] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class BootstrapManifest(BaseModel):
    """表示当前轮真正注入的 bootstrap 片段清单"""

    fragment_ids: list[str] = Field(default_factory=list)
    fragment_paths: list[str] = Field(default_factory=list)
    truncation_marks: list[str] = Field(default_factory=list)
    render_order: list[str] = Field(default_factory=list)
    total_token_cost: int = 0
