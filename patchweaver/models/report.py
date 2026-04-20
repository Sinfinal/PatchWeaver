"""最终报告模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from patchweaver.models.harness import ArtifactRef


class AttemptDigest(BaseModel):
    """表示单轮尝试的摘要信息。"""

    attempt_id: str
    attempt_no: int
    status: str
    failure_type: str | None = None


class FinalReport(BaseModel):
    """表示最终提交或归档的结构化结果。"""

    task_summary: dict[str, str] = Field(default_factory=dict)
    attempt_digest: list[AttemptDigest] = Field(default_factory=list)
    artifact_index: list[ArtifactRef] = Field(default_factory=list)
    final_status: str
    evaluation_summary: dict[str, object] = Field(default_factory=dict)
    explanations: list[str] = Field(default_factory=list)
