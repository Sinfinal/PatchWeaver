"""改写规划模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RewriteCandidate(BaseModel):
    """表示单个候选改写方案。"""

    candidate_id: str
    primitives: list[str] = Field(default_factory=list)
    target_functions: list[str] = Field(default_factory=list)
    expected_risk: float = 0.0
    expected_semantic_drift: float = 0.0
    expected_build_cost: float = 0.0


class RewritePlan(BaseModel):
    """表示当前轮选中的改写规划结果。"""

    task_id: str
    plan_id: str
    candidate_ids: list[str] = Field(default_factory=list)
    selected_recipe: str | None = None
    selected_primitives: list[str] = Field(default_factory=list)
    risk_coverage: float = 0.0
    notes: list[str] = Field(default_factory=list)

