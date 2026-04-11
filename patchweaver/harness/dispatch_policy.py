"""调度策略。"""

from __future__ import annotations


READ_ONLY_STAGES = {"retrieval", "semantic_card", "constraint_diagnosis", "failure_analysis", "reporting"}
WRITE_STAGES = {"rewrite", "rewrite_recipe", "build", "validate", "validation", "load", "unload"}


def dispatch_mode(stage_name: str) -> str:
    """根据阶段名判断调度模式。"""

    if stage_name in WRITE_STAGES:
        return "write-exclusive"
    if stage_name in READ_ONLY_STAGES:
        return "read-parallel"
    return "read-parallel"
