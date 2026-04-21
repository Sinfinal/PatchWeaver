"""调度策略"""

from __future__ import annotations


READ_ONLY_STAGES = {"retrieval", "semantic_card", "constraint_diagnosis", "failure_analysis", "reporting"}
WRITE_STAGES = {"rewrite", "rewrite_recipe", "build", "validate", "validation", "load", "unload"}


def is_write_stage(stage_name: str) -> bool:
    """判断阶段是否属于写入独占路径"""

    return stage_name in WRITE_STAGES


def dispatch_mode(stage_name: str, *, enable_read_parallel: bool = True) -> str:
    """根据阶段名判断调度模式"""

    if is_write_stage(stage_name):
        return "write-exclusive"
    if stage_name in READ_ONLY_STAGES and enable_read_parallel:
        return "read-parallel"
    return "read-serial"
