"""验证结果模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ValidationItem(BaseModel):
    """表示一项验证动作的结果。"""

    status: Literal["pending", "passed", "failed", "skipped"] = "pending"
    ok: bool = False
    detail: str = ""
    command: str | None = None
    log_path: str | None = None


class ValidationReport(BaseModel):
    """表示加载、卸载和语义校验的综合结果。"""

    load_result: ValidationItem = Field(default_factory=ValidationItem)
    unload_result: ValidationItem = Field(default_factory=ValidationItem)
    smoke_result: ValidationItem = Field(default_factory=ValidationItem)
    semantic_guard_result: ValidationItem = Field(default_factory=ValidationItem)
    notes: list[str] = Field(default_factory=list)
