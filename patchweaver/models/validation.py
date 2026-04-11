"""验证结果模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ValidationItem(BaseModel):
    """表示一项验证动作的结果。"""

    ok: bool = False
    detail: str = ""


class ValidationReport(BaseModel):
    """表示加载、卸载和语义校验的综合结果。"""

    load_result: ValidationItem = Field(default_factory=ValidationItem)
    unload_result: ValidationItem = Field(default_factory=ValidationItem)
    smoke_result: ValidationItem = Field(default_factory=ValidationItem)
    semantic_guard_result: ValidationItem = Field(default_factory=ValidationItem)
