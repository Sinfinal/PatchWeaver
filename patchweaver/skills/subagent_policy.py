"""只读子代理策略。"""

from __future__ import annotations


class SubagentPolicy:
    """负责判断当前阶段是否允许派生只读子代理。"""

    def allow(self, stage_name: str) -> bool:
        """仅对只读阶段返回允许。"""

        return stage_name in {"retrieval", "failure_analysis", "reporting"}

