"""补丁输入模型"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class SourceEvidence(BaseModel):
    """表示一条可追溯的补丁来源证据"""

    source_name: str
    url: str
    summary: str | None = None
    commit_id: str | None = None
    stage: str | None = None
    reference_type: str | None = None
    title: str | None = None
    preferred: bool = False


class PatchBundle(BaseModel):
    """表示任务对应的原始补丁和来源信息"""

    task_id: str
    cve_id: str
    upstream_commit: str | None = None
    stable_commit: str | None = None
    stable_source_baseline_ref: str | None = None
    commit_message: str | None = None
    affected_files: list[str] = Field(default_factory=list)
    raw_patch_path: Path | None = None
    normalized_patch_path: Path | None = None
    source_evidence: list[SourceEvidence] = Field(default_factory=list)
