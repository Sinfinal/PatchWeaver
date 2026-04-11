"""Harness 编排器。"""

from __future__ import annotations

from pathlib import Path

from patchweaver.models.harness import ArtifactRef, HarnessTrace, StateTransition, ToolCallRecord
from patchweaver.models.skill import SkillRouteDecision


class HarnessOrchestrator:
    """收敛单轮执行过程中产生的轨迹信息。"""

    def start_trace(self, *, trace_id: str, task_id: str, attempt_no: int) -> HarnessTrace:
        """创建一份新的 trace。"""

        return HarnessTrace(trace_id=trace_id, task_id=task_id, attempt_no=attempt_no)

    def record_stage(self, trace: HarnessTrace, *, from_stage: str, to_stage: str, reason: str) -> HarnessTrace:
        """记录状态迁移。"""

        updated = list(trace.state_transitions)
        updated.append(StateTransition(from_stage=from_stage, to_stage=to_stage, reason=reason))
        return trace.model_copy(update={"state_transitions": updated})

    def record_tool_call(self, trace: HarnessTrace, *, tool_name: str, action: str, status: str, detail: str = "") -> HarnessTrace:
        """记录一次工具调用。"""

        updated = list(trace.tool_calls)
        updated.append(ToolCallRecord(tool_name=tool_name, action=action, status=status, detail=detail))
        return trace.model_copy(update={"tool_calls": updated})

    def attach_route(self, trace: HarnessTrace, route: SkillRouteDecision) -> HarnessTrace:
        """把 skill 路由结果挂到 trace 上。"""

        return trace.model_copy(update={"skill_route": route})

    def attach_stage_route(self, trace: HarnessTrace, route: SkillRouteDecision) -> HarnessTrace:
        """按阶段写入路由摘要，方便后续回放。"""

        extras = dict(trace.extras)
        # stage_routes 单独放在 extras 里，后面 replay 拿这块就够了，不用再反解整份 trace。
        stage_routes = dict(extras.get("stage_routes", {}))
        stage_routes[route.stage_name] = {
            "selected_skill": route.selected_skill,
            "candidate_skills": route.candidate_skills,
            "selection_reason": route.selection_reason,
        }
        extras["stage_routes"] = stage_routes
        # 首次写入时保留一份主 route，外部快速查看时更方便。
        skill_route = trace.skill_route or route
        return trace.model_copy(update={"skill_route": skill_route, "extras": extras})

    def attach_dispatch_mode(self, trace: HarnessTrace, *, stage_name: str, mode: str) -> HarnessTrace:
        """记录阶段对应的调度模式。"""

        extras = dict(trace.extras)
        # 调度模式和状态迁移分开存，回放时查“为什么串行/为什么并行”会更直接。
        dispatch_modes = dict(extras.get("dispatch_modes", {}))
        dispatch_modes[stage_name] = mode
        extras["dispatch_modes"] = dispatch_modes
        return trace.model_copy(update={"extras": extras})

    def attach_artifact(self, trace: HarnessTrace, *, artifact_type: str, artifact_path: Path, summary: str = "") -> HarnessTrace:
        """把关键产物挂到 trace 上。"""

        # trace 里只挂关键索引，不把文件内容直接塞进去，避免回放包越来越重。
        artifacts = list(trace.artifacts)
        artifacts.append(ArtifactRef(artifact_type=artifact_type, artifact_path=artifact_path, summary=summary))
        return trace.model_copy(update={"artifacts": artifacts})
