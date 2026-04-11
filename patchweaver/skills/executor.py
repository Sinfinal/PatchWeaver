"""Skill 执行器骨架。"""

from __future__ import annotations

from patchweaver.skills.contracts import SkillExecutionRequest, SkillExecutionResult


class DefaultSkillExecutor:
    """负责执行最小占位 skill。"""

    def execute(self, request: SkillExecutionRequest) -> SkillExecutionResult:
        """返回占位执行结果。"""

        return SkillExecutionResult(ok=True, summary=f"{request.stage_name} 阶段占位执行完成。")

