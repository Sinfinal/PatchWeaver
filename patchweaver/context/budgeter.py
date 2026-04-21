"""上下文预算器"""

from __future__ import annotations


class ContextBudgeter:
    """负责给不同阶段计算上下文预算"""

    STAGE_LIMITS = {
        "retrieval": {"token_limit": 5200, "stage_weight": 1},
        "semantic_card": {"token_limit": 4200, "stage_weight": 1},
        "constraint_diagnosis": {"token_limit": 4200, "stage_weight": 1},
        "rewrite_recipe": {"token_limit": 5000, "stage_weight": 2},
        "failure_analysis": {"token_limit": 3600, "stage_weight": 1},
        "validation": {"token_limit": 3400, "stage_weight": 1},
        "reporting": {"token_limit": 3200, "stage_weight": 1},
    }

    def budget_for(self, stage_name: str) -> dict[str, int]:
        """返回当前阶段的默认预算"""

        if not stage_name:
            return {"token_limit": 4000, "stage_weight": 0}
        return dict(self.STAGE_LIMITS.get(stage_name, {"token_limit": 4000, "stage_weight": 1}))
