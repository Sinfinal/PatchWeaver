"""Chat assistant request and response schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request payload for the read-only Web chat assistant."""

    message: str
    session_id: str = ""
    context: dict[str, str] = Field(default_factory=dict)


class ToolCallTrace(BaseModel):
    """Public trace for one assistant tool call."""

    name: str
    status: Literal["success", "error", "skipped"]
    summary: str = ""


class SuggestedAction(BaseModel):
    """User-confirmed action proposal returned by the assistant."""

    type: str
    label: str
    payload: dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = False


class ChatResponse(BaseModel):
    """Structured assistant response rendered by the Web drawer."""

    answer: str
    evidence_refs: list[str] = Field(default_factory=list)
    tool_calls: list[ToolCallTrace] = Field(default_factory=list)
    suggested_actions: list[SuggestedAction] = Field(default_factory=list)
    risk: Literal["low", "medium", "high"] = "low"
    requires_confirmation: bool = False
    session_id: str = ""
