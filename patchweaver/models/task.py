"""任务上下文模型。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    """返回当前 UTC 时间。"""

    return datetime.now(timezone.utc)


class TaskContext(BaseModel):
    """表示任务在主状态机中的全局上下文。"""

    task_id: str
    cve_id: str
    target_kernel: str
    status: str = "created"
    max_attempts: int = 5
    current_attempt: int = 0
    workspace_dir: Path
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

