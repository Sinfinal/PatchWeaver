"""Failover 记录模型。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    """返回当前 UTC 时间。"""

    return datetime.now(timezone.utc)


class FailoverRecord(BaseModel):
    """表示一次窄状态回退记录。"""

    stage_name: str
    trigger_reason: str
    from_profile: str
    to_profile: str
    field_changes: dict[str, Any] = Field(default_factory=dict)
    result: str
    created_at: datetime = Field(default_factory=_utc_now)

