"""语义卡片模型"""

from __future__ import annotations

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
