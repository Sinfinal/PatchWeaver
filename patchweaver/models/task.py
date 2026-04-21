"""任务上下文模型"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    """返回当前 UTC 时间"""

    return datetime.now(timezone.utc)


class TaskContext(BaseModel):
    """表示任务在主状态机中的全局上下文"""

    task_id: str
    cve_id: str
    target_kernel: str
    target_kernel_source: Literal["cli_override", "detected_build_env", "detected_machine", "config_fallback"] | None = None
    profile_name: str | None = None
    status: str = "created"
    max_attempts: int = 5
    current_attempt: int = 0
    workspace_dir: Path
    machine_profile: "MachineProfile | None" = None
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class MachineProfile(BaseModel):
    """记录任务创建或运行时绑定到的机器与构建环境快照"""

    machine_system: str | None = None
    machine_kernel: str | None = None
    machine_arch: str | None = None
    hostname: str | None = None
    build_target_kernel: str | None = None
    build_target_kernel_source: str | None = None
    build_backend: str | None = None
    builder_cmd: str | None = None
    builder_path: str | None = None
    selected_source_dir: str | None = None
    selected_source_reason: str | None = None
    config_path: str | None = None
    vmlinux_path: str | None = None
    detected_at: datetime = Field(default_factory=_utc_now)
