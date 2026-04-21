"""环境诊断模型"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DoctorCheck(BaseModel):
    """表示一项环境检查结果"""

    category: str
    name: str
    label: str
    ok: bool
    status: str
    detail: str


class DoctorReport(BaseModel):
    """表示一次环境诊断的结构化结果"""

    runtime: dict[str, str] = Field(default_factory=dict)
    checks: list[DoctorCheck] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)

