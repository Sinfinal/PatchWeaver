"""尝试轮模型。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    """返回当前 UTC 时间。"""

    return datetime.now(timezone.utc)


class AttemptState(BaseModel):
    """表示主状态机当前轮的运行状态。"""

    task_id: str
    attempt_no: int
    stage: str
    remaining_budget: dict[str, Any] = Field(default_factory=dict)
    disabled_strategies: list[str] = Field(default_factory=list)
    termination_reason: str | None = None


class AttemptRecord(BaseModel):
    """表示单轮构建尝试的结果。"""

    task_id: str
    attempt_no: int
    attempt_id: str
    candidate_id: str | None = None
    status: str
    failure_type: str | None = None
    build_log_path: Path | None = None
    module_path: Path | None = None
    rewritten_patch_path: Path | None = None
    started_at: datetime = Field(default_factory=_utc_now)
    finished_at: datetime | None = None


class FailureRecord(BaseModel):
    """表示一次结构化失败归因结果。"""

    task_id: str
    attempt_id: str
    stage_name: str
    failure_type: str
    summary: str
    evidence: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)

