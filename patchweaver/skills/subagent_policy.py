"""只读子代理策略。"""

from __future__ import annotations


class SubagentPolicy:
    """负责判断当前阶段是否允许派生只读子代理。"""

    def __init__(
        self,
        *,
        allow_readonly_subagent: bool = True,
        allowed_stages: list[str] | None = None,
        max_parallel: int = 2,
    ) -> None:
        """记录只读子代理的允许范围。"""

        self.allow_readonly_subagent = allow_readonly_subagent
        self.allowed_stages = set(allowed_stages or ["retrieval", "failure_analysis", "reporting"])
        self.max_parallel = max_parallel

    def allow(self, stage_name: str) -> bool:
        """仅对只读阶段返回允许。"""

        return self.allow_readonly_subagent and stage_name in self.allowed_stages
