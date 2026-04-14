"""经验记忆模型。"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    """返回当前 UTC 时间。"""

    return datetime.now(timezone.utc)


class FailureMemoryEntry(BaseModel):
    """表示一条失败经验条目。"""

    entry_id: str
    task_id: str
    cve_id: str
    attempt_id: str
    stage_name: str
    failure_type: str
    summary: str
    recipe_name: str | None = None
    candidate_id: str | None = None
    evidence: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)


class RecipeMemoryEntry(BaseModel):
    """表示一条配方经验条目。"""

    entry_id: str
    recipe_name: str
    risk_types: list[str] = Field(default_factory=list)
    primitives: list[str] = Field(default_factory=list)
    candidate_id: str | None = None
    last_task_id: str | None = None
    last_attempt_id: str | None = None
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    last_status: str = "unknown"
    last_summary: str = ""
    updated_at: datetime = Field(default_factory=_utc_now)
