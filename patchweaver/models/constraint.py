"""热补丁约束模型"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RiskItem(BaseModel):
    """表示一项热补丁风险"""

    risk_type: str
    severity: str
    evidence: list[str] = Field(default_factory=list)
    affected_functions: list[str] = Field(default_factory=list)
    required_primitives: list[str] = Field(default_factory=list)


class ConstraintReport(BaseModel):
    """表示补丁的热补丁约束分析结果"""

    task_id: str
    risk_items: list[RiskItem] = Field(default_factory=list)
    high_risk_count: int = 0
    requires_callback: bool = False
    requires_shadow_variable: bool = False
    summary: str | None = None

