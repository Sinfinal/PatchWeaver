"""证据片段模型"""

from __future__ import annotations

from pydantic import BaseModel, Field


class EvidenceSpan(BaseModel):
    """表示一段可追溯的证据片段"""

    evidence_id: str
    source_type: str
    source_path: str
    excerpt: str
    start_line: int | None = None
    end_line: int | None = None
    score: float = 0.0


class EvidenceBundle(BaseModel):
    """表示当前阶段收集到的证据集合"""

    evidence_ids: list[str] = Field(default_factory=list)
    spans: list[EvidenceSpan] = Field(default_factory=list)
    memory_hits: list[str] = Field(default_factory=list)

