"""模型交互记录模型"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    """返回当前 UTC 时间"""

    return datetime.now(timezone.utc)


class ModelInteractionRecord(BaseModel):
    """表示一次模型调用的结构化留痕"""

    record_type: Literal["model_interaction"] = "model_interaction"
    created_at: datetime = Field(default_factory=_utc_now)
    stage_name: str
    task_id: str
    attempt_no: int | None = None
    status: Literal["applied", "failed"] = "applied"
    success: bool = True
    provider: str | None = None
    endpoint_mode: str | None = None
    topology: str | None = None
    model_name: str | None = None
    selected_skill: str | None = None
    route_source: str | None = None
    prompt_packet_path: str | None = None
    source_evidence_path: str | None = None
    artifact_path: str | None = None
    failure_reason: str | None = None
    duration_ms: int | None = None
    context_token_cost: int = 0
    context_evidence_count: int = 0
    context_duplicate_hits: int = 0
    context_memory_hits: int = 0
    evidence_ids: list[str] = Field(default_factory=list)
    budget_snapshot: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, Any] = Field(default_factory=dict)
    record_mode: Literal["off", "basic", "full"] = "basic"
    request_char_count: int = 0
    system_prompt_chars: int = 0
    user_prompt_chars: int = 0
    response_chars: int = 0
    system_prompt_preview: str | None = None
    user_prompt_preview: str | None = None
    response_preview: str | None = None
    parsed_payload_keys: list[str] = Field(default_factory=list)
    system_prompt: str | None = None
    user_prompt: str | None = None
    raw_response_text: str | None = None
    parsed_payload: dict[str, Any] | None = None
