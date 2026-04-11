"""提示包模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PromptPacket(BaseModel):
    """表示某个阶段最终送入模型的提示包。"""

    stage_name: str
    system_prompt_version: str
    worker_prompt_version: str
    schema_name: str
    budget_snapshot: dict[str, Any] = Field(default_factory=dict)
    bootstrap_fragments: list[str] = Field(default_factory=list)
    prompt_sections: list[str] = Field(default_factory=list)

