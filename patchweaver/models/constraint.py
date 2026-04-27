"""热补丁约束模型"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RiskItem(BaseModel):
    """表示一项热补丁风险"""

    risk_type: str
    severity: str
    summary: str | None = None
    source_rule: str | None = None
    evidence: list[str] = Field(default_factory=list)
    affected_files: list[str] = Field(default_factory=list)
    affected_functions: list[str] = Field(default_factory=list)
    affected_conditions: list[str] = Field(default_factory=list)
    critical_calls: list[str] = Field(default_factory=list)
    required_primitives: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)


class RouteHint(BaseModel):
    """表示约束报告给规划层的路线提示"""

    route_name: str
    summary: str
    recommended_primitives: list[str] = Field(default_factory=list)
    blocking_risk_types: list[str] = Field(default_factory=list)
    preferred: bool = False


class ConstraintReport(BaseModel):
    """表示补丁的热补丁约束分析结果"""

    task_id: str
    semantic_card_source: Literal["deterministic", "enriched", "unavailable"] = "unavailable"
    semantic_card_enriched: bool = False
    target_files: list[str] = Field(default_factory=list)
    target_functions: list[str] = Field(default_factory=list)
    risk_items: list[RiskItem] = Field(default_factory=list)
    dominant_risk_types: list[str] = Field(default_factory=list)
    suggested_primitives: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    route_hints: list[RouteHint] = Field(default_factory=list)
    candidate_routes: list[str] = Field(default_factory=list)
    preferred_route: str | None = None
    high_risk_count: int = 0
    requires_callback: bool = False
    requires_shadow_variable: bool = False
    direct_apply_viable: bool = False
    direct_apply_recommended: bool = False
    direct_apply_role: Literal["primary", "fallback", "blocked"] = "blocked"
    summary: str | None = None
