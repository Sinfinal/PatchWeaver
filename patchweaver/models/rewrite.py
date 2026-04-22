"""改写规划模型"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class RewriteCandidate(BaseModel):
    """表示单个候选改写方案"""

    candidate_id: str
    recipe_name: str
    primitives: list[str] = Field(default_factory=list)
    target_functions: list[str] = Field(default_factory=list)
    rule_hits: list[str] = Field(default_factory=list)
    expected_risk: float = 0.0
    expected_semantic_drift: float = 0.0
    expected_build_cost: float = 0.0
    history_success_rate: float = 0.0
    failure_pressure: float = 0.0
    ranking_score: float = 0.0
    ranking_reasons: list[str] = Field(default_factory=list)


class RewritePlan(BaseModel):
    """表示当前轮选中的改写规划结果"""

    task_id: str
    plan_id: str
    candidate_ids: list[str] = Field(default_factory=list)
    selected_recipe: str | None = None
    selected_primitives: list[str] = Field(default_factory=list)
    target_files: list[str] = Field(default_factory=list)
    rule_hits: list[str] = Field(default_factory=list)
    risk_coverage: float = 0.0
    selection_reason: str | None = None
    notes: list[str] = Field(default_factory=list)
    candidate_summaries: list[RewriteCandidate] = Field(default_factory=list)


class TransformationStep(BaseModel):
    """记录单个改写步骤的执行轨迹"""

    step_id: str
    engine: Literal["template", "smpl", "diff_editor", "apply_precheck"]
    action: str
    recipe_name: str | None = None
    primitive: str | None = None
    target_files: list[str] = Field(default_factory=list)
    summary: str | None = None


class TransformationTrace(BaseModel):
    """表示一次改写的完整变换轨迹"""

    task_id: str
    plan_id: str
    source_patch_path: Path | None = None
    rewritten_patch_path: Path | None = None
    steps: list[TransformationStep] = Field(default_factory=list)


class ApplyPrecheckReport(BaseModel):
    """表示构建前 apply 级别预检查结果"""

    status: Literal["passed", "failed", "skipped"]
    ok: bool = False
    backend: str
    target_source_dir: str | None = None
    command: str | None = None
    checked_patch_path: str | None = None
    exit_code: int | None = None
    summary: str
    stdout: str | None = None
    stderr: str | None = None
    failure_type: str | None = None
    build_exec_status: str | None = None
    target_state: str | None = None

