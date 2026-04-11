"""上下文预算器。"""

from __future__ import annotations


class ContextBudgeter:
    """负责给不同阶段计算上下文预算。"""

    def budget_for(self, stage_name: str) -> dict[str, int]:
        """返回当前阶段的默认预算。"""

        return {"token_limit": 4000, "stage_weight": 1 if stage_name else 0}

