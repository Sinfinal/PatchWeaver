"""Skill 执行器骨架"""

from __future__ import annotations

from patchweaver.skills.contracts import SkillExecutionRequest, SkillExecutionResult


class DefaultSkillExecutor:
    """负责执行最小占位 skill"""

    def execute(self, request: SkillExecutionRequest) -> SkillExecutionResult:
        """返回占位执行结果"""

        selected_skill = str(request.payload.get("selected_skill") or "direct_worker")
        expected_outputs = [str(item) for item in request.payload.get("expected_outputs") or []]
        return SkillExecutionResult(
            ok=True,
            summary=f"{request.stage_name} 阶段已按 {selected_skill} 契约执行最小流程。",
            payload={"selected_skill": selected_skill, "expected_outputs": expected_outputs},
        )
