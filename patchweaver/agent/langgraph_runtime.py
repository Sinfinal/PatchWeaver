"""LangGraph-style dev runtime for Agent-driven auto-run orchestration."""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from patchweaver.agent.actions import AgentActionName
from patchweaver.agent.observability import build_langgraph_observability_event, emit_observability_event
from patchweaver.agent.planner import LLMPlanner
from patchweaver.agent.planning_contracts import AgentGoal, ReflectionRecord, TaskPlan, ToolResult
from patchweaver.agent.policy_guard import PolicyGuard, PolicyGuardResult
from patchweaver.agent.reflection import (
    build_memory_hints_from_reflections,
    generate_reflection,
    load_reflections_for_next_attempt,
    mark_memory_usage,
    save_reflection,
)
from patchweaver.agent.state import AgentObservation, sanitize_agent_payload
from patchweaver.config.models import ModelsConfig
from patchweaver.memory.dual_memory import DualMemory
from patchweaver.models.attempt import FailureRecord
from patchweaver.models.task import TaskContext
from patchweaver.models.validation import ValidationReport
from patchweaver.utils.path_policy import to_project_relative

GRAPH_NODES = ["observe", "plan", "guard", "execute", "reflect", "reduce", "route"]
AUTO_RUN_AVAILABLE_ACTIONS = [
    AgentActionName.ANALYZE_SOURCE,
    AgentActionName.ANALYZE_TASK,
    AgentActionName.RUN_ATTEMPT,
    AgentActionName.RUN_TASK,
    AgentActionName.REPORT,
    AgentActionName.REPORT_TASK,
    AgentActionName.REPLAY,
    AgentActionName.REPLAY_TASK,
    AgentActionName.RETRY_WITH_STRATEGY,
    AgentActionName.STOP_MANUAL_REVIEW,
]


class LangGraphRuntimeResult(BaseModel):
    """Public result returned by the dev Agent graph runtime."""

    task_id: str
    runtime: str = "langgraph"
    status: str
    terminal: bool = False
    actions: list[dict[str, Any]] = Field(default_factory=list)
    plans: list[dict[str, Any]] = Field(default_factory=list)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    trace_path: str | None = None
    checkpoint_path: str | None = None
    resumed_from_checkpoint: bool = False


class LangGraphRuntime:
    """Run Web/API auto-run through Planner -> Guard -> Registry nodes."""

    PLAN_TO_EXECUTABLE_ACTION = {
        AgentActionName.ANALYZE_SOURCE: AgentActionName.ANALYZE_TASK,
        AgentActionName.ANALYZE_TASK: AgentActionName.ANALYZE_TASK,
        AgentActionName.RUN_ATTEMPT: AgentActionName.RUN_TASK,
        AgentActionName.RUN_TASK: AgentActionName.RUN_TASK,
        AgentActionName.RETRY_WITH_STRATEGY: AgentActionName.RUN_TASK,
        AgentActionName.REPORT: AgentActionName.REPORT_TASK,
        AgentActionName.REPORT_TASK: AgentActionName.REPORT_TASK,
        AgentActionName.REPLAY: AgentActionName.REPLAY_TASK,
        AgentActionName.REPLAY_TASK: AgentActionName.REPLAY_TASK,
        AgentActionName.GET_TASK_DETAIL: AgentActionName.GET_TASK_DETAIL,
        AgentActionName.STOP_MANUAL_REVIEW: AgentActionName.STOP_MANUAL_REVIEW,
    }

    TERMINAL_ACTIONS = {
        AgentActionName.STOP_MANUAL_REVIEW,
        AgentActionName.REPLAY_TASK,
    }

    def __init__(
        self,
        *,
        task_repo: Any,
        attempt_repo: Any,
        action_registry: Any,
        artifact_repo: Any | None = None,
        project_root: Path | None = None,
        models_config: ModelsConfig | None = None,
        planner: Any | None = None,
        guard: PolicyGuard | None = None,
        memory: DualMemory | None = None,
        max_steps: int = 8,
    ) -> None:
        self.task_repo = task_repo
        self.attempt_repo = attempt_repo
        self.action_registry = action_registry
        self.artifact_repo = artifact_repo
        self.project_root = project_root.resolve() if project_root is not None else None
        self.models_config = models_config
        self.planner = planner or LLMPlanner(project_root=project_root, models_config=models_config)
        self.guard = guard or PolicyGuard()
        self.memory = memory
        self.max_steps = max(1, int(max_steps))
        self.langgraph_available = importlib.util.find_spec("langgraph") is not None

    def run(self, task_id: str, *, resume: bool = True) -> dict[str, Any]:
        """Run a task until the graph routes to terminal or max_steps is reached."""

        task = self._require_task(task_id)
        trace_path = task.workspace_dir / "agent" / "agent_auto_workflow_trace.json"
        checkpoint_path = task.workspace_dir / "agent" / "langgraph_checkpoint.json"
        trace = self._load_trace(task=task, trace_path=trace_path)
        checkpoint = self._load_checkpoint(checkpoint_path) if resume else {}
        resumed = bool(checkpoint and not checkpoint.get("terminal"))

        actions: list[dict[str, Any]] = []
        plans: list[dict[str, Any]] = []
        tool_results: list[dict[str, Any]] = []
        status = "ok"
        terminal = False
        last_observation: AgentObservation | None = None
        last_plan: TaskPlan | None = None
        last_guard: PolicyGuardResult | None = None
        last_tool_result: ToolResult | None = None

        for step_index in range(1, self.max_steps + 1):
            observation, failure_record, reflections = self._observe(task_id)
            last_observation = observation
            self._record_node(
                trace,
                checkpoint_path=checkpoint_path,
                node="observe",
                step_index=step_index,
                status="ok",
                payload={
                    "observation": observation.model_dump(mode="json"),
                    "reflection_count": len(reflections),
                },
            )
            self._write_trace(trace_path, trace)

            goal = AgentGoal.from_task_context(self._require_task(task_id))
            planner = self._planner_for_task(task)
            plan = planner.plan(
                observation=observation,
                goal=goal,
                memory_hints=observation.memory_hints,
                available_actions=AUTO_RUN_AVAILABLE_ACTIONS,
                reflections=reflections,
            )
            last_plan = plan
            plans.append(plan.model_dump(mode="json"))
            self._record_node(
                trace,
                checkpoint_path=checkpoint_path,
                node="plan",
                step_index=step_index,
                status="ok",
                payload={"plan": plan.model_dump(mode="json")},
            )
            self._write_trace(trace_path, trace)

            guard_result = self.guard.validate_plan(plan, observation)
            last_guard = guard_result
            self._record_node(
                trace,
                checkpoint_path=checkpoint_path,
                node="guard",
                step_index=step_index,
                status="ok" if guard_result.allowed else "rejected",
                payload={"guard": guard_result.model_dump(mode="json")},
            )
            self._write_trace(trace_path, trace)

            if not guard_result.allowed:
                tool_result = ToolResult(
                    action_name=plan.selected_action,
                    task_id=task_id,
                    status="rejected",
                    error=guard_result.reject_reason,
                    metadata={"guard_rejected": True, "terminal": guard_result.terminal},
                )
                terminal = guard_result.terminal or True
                status = "terminal" if terminal else "failed"
                reflection_observation = observation
            else:
                action_name = self._to_executable_action(plan.selected_action)
                action_result = self.action_registry.execute(
                    action_name,
                    task_id,
                    failure_record=failure_record,
                    memory_hints=observation.memory_hints,
                    single_attempt=True,
                )
                after_observation, _, _ = self._observe(task_id)
                progress_made = self._progress_made(before=observation, after=after_observation)
                action_payload = action_result.model_dump(mode="json")
                actions.append(action_payload)
                tool_result = ToolResult(
                    action_name=action_name,
                    task_id=task_id,
                    status=str(getattr(action_result, "status", "ok")),
                    artifact_paths=[getattr(action_result, "trace_path")] if getattr(action_result, "trace_path", None) else [],
                    error=getattr(action_result, "error", None),
                    metadata={
                        "planner_action": plan.selected_action.value,
                        "executable_action": action_name.value,
                        "action_terminal": bool(getattr(action_result, "terminal", False)),
                        "progress_made": progress_made,
                        "after_failure_type": after_observation.failure_type,
                        "after_task_status": after_observation.task_status,
                        "after_validation_status": after_observation.validation_status,
                    },
                )
                terminal = bool(getattr(action_result, "terminal", False)) or action_name in self.TERMINAL_ACTIONS
                status = "terminal" if terminal else "ok"
                reflection_observation = after_observation if after_observation.failure_type else observation

            tool_result = mark_memory_usage(tool_result=tool_result, plan=plan, reflections=reflections)
            last_tool_result = tool_result
            tool_results.append(tool_result.model_dump(mode="json"))
            self._record_node(
                trace,
                checkpoint_path=checkpoint_path,
                node="execute",
                step_index=step_index,
                status=tool_result.status,
                payload={"tool_result": tool_result.model_dump(mode="json")},
            )
            self._write_trace(trace_path, trace)

            reflection = self._reflect(
                observation=reflection_observation,
                tool_result=tool_result,
                task_workspace=task.workspace_dir,
                failure_record=failure_record,
            )
            self._record_node(
                trace,
                checkpoint_path=checkpoint_path,
                node="reflect",
                step_index=step_index,
                status="ok",
                payload={"reflection": reflection.model_dump(mode="json") if reflection is not None else None},
            )
            self._write_trace(trace_path, trace)

            reduction = self._reduce(
                observation=observation,
                plan=plan,
                guard_result=guard_result,
                tool_result=tool_result,
                terminal=terminal,
            )
            self._record_node(
                trace,
                checkpoint_path=checkpoint_path,
                node="reduce",
                step_index=step_index,
                status="ok",
                payload={"reduction": reduction},
            )
            self._write_trace(trace_path, trace)

            route = self._route(
                plan=plan,
                tool_result=tool_result,
                terminal=terminal,
                step_index=step_index,
            )
            self._record_node(
                trace,
                checkpoint_path=checkpoint_path,
                node="route",
                step_index=step_index,
                status=route["status"],
                payload={"route": route},
            )
            self._write_trace(trace_path, trace)
            self._write_checkpoint(
                checkpoint_path,
                {
                    "task_id": task_id,
                    "runtime": "langgraph",
                    "step_index": step_index,
                    "completed_nodes": GRAPH_NODES,
                    "next_node": None if route["terminal"] else "observe",
                    "terminal": route["terminal"],
                    "last_action": tool_result.action_name.value,
                    "last_plan": plan.model_dump(mode="json"),
                    "last_observation": observation.model_dump(mode="json"),
                },
            )

            if route["terminal"]:
                terminal = True
                status = "terminal"
                break

        if not terminal and status == "ok":
            status = "ok"

        payload = LangGraphRuntimeResult(
            task_id=task_id,
            status=status,
            terminal=terminal,
            actions=actions,
            plans=plans,
            tool_results=tool_results,
            trace_path=to_project_relative(self.project_root, trace_path),
            checkpoint_path=to_project_relative(self.project_root, checkpoint_path),
            resumed_from_checkpoint=resumed,
        ).model_dump(mode="json")
        trace["summary"] = payload
        trace["last_observation"] = last_observation.model_dump(mode="json") if last_observation is not None else None
        trace["last_plan"] = last_plan.model_dump(mode="json") if last_plan is not None else None
        trace["last_guard"] = last_guard.model_dump(mode="json") if last_guard is not None else None
        trace["last_tool_result"] = last_tool_result.model_dump(mode="json") if last_tool_result is not None else None
        self._write_trace(trace_path, trace)
        self._add_trace_artifact(
            task_id=task_id,
            trace_path=trace_path,
            checkpoint_path=checkpoint_path,
            planner_trace_path=task.workspace_dir / "agent" / "agent_planner_trace.json",
        )
        return payload

    def _planner_for_task(self, task: TaskContext) -> Any:
        if isinstance(self.planner, LLMPlanner):
            self.planner.trace_path = task.workspace_dir / "agent" / "agent_planner_trace.json"
        return self.planner

    def _observe(self, task_id: str) -> tuple[AgentObservation, FailureRecord | None, list[ReflectionRecord]]:
        task = self._require_task(task_id)
        attempts = self._list_attempts(task_id)
        latest_attempt = attempts[-1] if attempts else None
        failure_record = self._load_failure_record(task=task, latest_attempt=latest_attempt)
        validation_report = self._load_validation_report(task=task, latest_attempt=latest_attempt)
        reflections = load_reflections_for_next_attempt(task.workspace_dir, self.memory)
        memory_hints = build_memory_hints_from_reflections(reflections)
        observation = AgentObservation.from_runtime(
            task=task,
            latest_attempt=latest_attempt,
            failure_record=failure_record,
            validation_report=validation_report,
            memory_hints=memory_hints,
        )
        diagnostics = dict(observation.diagnostics)
        diagnostics["artifact_state"] = self._artifact_state(task=task)
        observation = observation.model_copy(update={"diagnostics": sanitize_agent_payload(diagnostics)})
        return observation, failure_record, reflections

    def _reflect(
        self,
        *,
        observation: AgentObservation,
        tool_result: ToolResult,
        task_workspace: Path,
        failure_record: FailureRecord | None,
    ) -> ReflectionRecord | None:
        if observation.failure_type in {None, "", "none"}:
            return None
        task = self._require_task(observation.task_id)
        reflection = generate_reflection(observation, tool_result, models_config=self.models_config)
        save_reflection(
            reflection,
            task_workspace,
            memory=self.memory,
            task=task,
            failure_record=failure_record,
        )
        return reflection

    def _reduce(
        self,
        *,
        observation: AgentObservation,
        plan: TaskPlan,
        guard_result: PolicyGuardResult,
        tool_result: ToolResult,
        terminal: bool,
    ) -> dict[str, Any]:
        return sanitize_agent_payload(
            {
                "task_id": observation.task_id,
                "selected_action": plan.selected_action.value,
                "executable_action": tool_result.action_name.value,
                "guard_allowed": guard_result.allowed,
                "terminal": terminal,
                "failure_type": observation.failure_type,
                "memory_not_used": tool_result.metadata.get("memory_not_used"),
            }
        )

    def _route(
        self,
        *,
        plan: TaskPlan,
        tool_result: ToolResult,
        terminal: bool,
        step_index: int,
    ) -> dict[str, Any]:
        if terminal:
            return {"status": "terminal", "terminal": True, "reason": "流程已到终止动作或安全检查终止"}
        if tool_result.status in {"failed", "rejected"}:
            if (
                tool_result.action_name == AgentActionName.ANALYZE_TASK
                and tool_result.metadata.get("after_failure_type") in {
                    "source_unavailable",
                    "build_env_missing",
                    "kernel_src_missing",
                    "kernel_config_missing",
                    "vmlinux_missing",
                    "build_cache_incomplete",
                }
            ):
                return {
                    "status": "continue",
                    "terminal": False,
                    "reason": "分析阶段生成终止型失败观察，交由规划器复核",
                }
            return {"status": "terminal", "terminal": True, "reason": tool_result.error or tool_result.status}
        if (
            tool_result.action_name == AgentActionName.RUN_TASK
            and tool_result.metadata.get("progress_made") is False
        ):
            return {"status": "no_progress", "terminal": True, "reason": "构建动作未带来新的任务状态变化"}
        if step_index >= self.max_steps:
            return {"status": "max_steps", "terminal": True, "reason": "自动编排达到最大步数"}
        return {"status": "continue", "terminal": False, "reason": f"规划器选择 {plan.selected_action.value}"}

    def _progress_made(self, *, before: AgentObservation, after: AgentObservation) -> bool:
        before_key = (
            before.task_status,
            before.current_attempt,
            before.latest_attempt_no,
            before.latest_status,
            before.failure_type,
            before.validation_status,
            before.diagnostics.get("artifact_state"),
            tuple(before.evidence_refs),
        )
        after_key = (
            after.task_status,
            after.current_attempt,
            after.latest_attempt_no,
            after.latest_status,
            after.failure_type,
            after.validation_status,
            after.diagnostics.get("artifact_state"),
            tuple(after.evidence_refs),
        )
        return before_key != after_key

    def _to_executable_action(self, action: AgentActionName) -> AgentActionName:
        return self.PLAN_TO_EXECUTABLE_ACTION[action]

    def _require_task(self, task_id: str) -> TaskContext:
        task = self.task_repo.get_task(task_id)
        if task is None:
            raise ValueError(f"未找到任务：{task_id}")
        return task

    def _list_attempts(self, task_id: str) -> list[Any]:
        if not hasattr(self.attempt_repo, "list_attempts"):
            return []
        return list(self.attempt_repo.list_attempts(task_id))

    def _load_failure_record(self, *, task: TaskContext, latest_attempt: Any | None) -> FailureRecord | None:
        candidates: list[Path] = []
        if latest_attempt is not None:
            candidates.append(task.workspace_dir / "attempts" / f"{latest_attempt.attempt_no:03d}" / "logs" / "failure_record.json")
        candidates.append(task.workspace_dir / "analysis" / "trace" / "failure_record.json")
        for path in candidates:
            if not path.exists():
                continue
            try:
                return FailureRecord.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        return None

    def _load_validation_report(self, *, task: TaskContext, latest_attempt: Any | None) -> ValidationReport | None:
        if latest_attempt is None:
            return None
        attempt_no = getattr(latest_attempt, "attempt_no", None)
        if attempt_no is None:
            return None
        path = task.workspace_dir / "attempts" / f"{int(attempt_no):03d}" / "artifacts" / "validation_report.json"
        if not path.exists():
            return None
        try:
            return ValidationReport.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return None

    def _artifact_state(self, *, task: TaskContext) -> dict[str, Any]:
        trace_path = task.workspace_dir / "agent" / "agent_auto_workflow_trace.json"
        replay_recorded = False
        if trace_path.exists():
            try:
                trace = json.loads(trace_path.read_text(encoding="utf-8") or "{}")
            except (OSError, json.JSONDecodeError):
                trace = {}
            nodes = trace.get("nodes") if isinstance(trace, dict) else None
            if isinstance(nodes, list):
                replay_recorded = any(
                    isinstance(node, dict)
                    and node.get("node") == "execute"
                    and (((node.get("payload") or {}).get("tool_result") or {}).get("action_name") == "replay_task")
                    for node in nodes
                )
        reports_dir = task.workspace_dir / "reports"
        return {
            "report_json_exists": (reports_dir / "report.json").exists(),
            "report_md_exists": (reports_dir / "report.md").exists(),
            "evaluation_summary_exists": (reports_dir / "evaluation_summary.json").exists(),
            "replay_recorded": replay_recorded,
        }

    def _load_trace(self, *, task: TaskContext, trace_path: Path) -> dict[str, Any]:
        if trace_path.exists():
            try:
                payload = json.loads(trace_path.read_text(encoding="utf-8") or "{}")
                if isinstance(payload, dict):
                    return payload
            except json.JSONDecodeError:
                pass
        return {
            "task_id": task.task_id,
            "cve_id": task.cve_id,
            "target_kernel": task.target_kernel,
            "runtime": "langgraph",
            "langgraph_available": self.langgraph_available,
            "graph_nodes": GRAPH_NODES,
            "nodes": [],
            "plans": [],
            "tool_results": [],
        }

    def _record_node(
        self,
        trace: dict[str, Any],
        *,
        checkpoint_path: Path,
        node: str,
        step_index: int,
        status: str,
        payload: dict[str, Any],
    ) -> None:
        node_payload = {
            "node": node,
            "step_index": step_index,
            "status": status,
            "at": datetime.now(timezone.utc).isoformat(),
            "payload": sanitize_agent_payload(payload),
        }
        trace.setdefault("nodes", []).append(node_payload)
        if node == "plan" and payload.get("plan") is not None:
            trace.setdefault("plans", []).append(payload["plan"])
        if node == "execute" and payload.get("tool_result") is not None:
            trace.setdefault("tool_results", []).append(payload["tool_result"])
        self._write_checkpoint(
            checkpoint_path,
            {
                "task_id": trace.get("task_id"),
                "runtime": "langgraph",
                "step_index": step_index,
                "completed_node": node,
                "next_node": self._next_node(node),
                "terminal": False,
                "last_node_payload": node_payload,
            },
        )
        try:
            event = build_langgraph_observability_event(
                task_id=str(trace.get("task_id") or ""),
                cve_id=str(trace.get("cve_id") or ""),
                target_kernel=str(trace.get("target_kernel") or ""),
                node=node,
                step_index=step_index,
                status=status,
                payload=payload,
                trace_path=str(trace.get("trace_path") or ""),
            )
            emit_observability_event(event=event, workspace_dir=checkpoint_path.parent.parent)
        except Exception:
            return None

    def _next_node(self, node: str) -> str | None:
        try:
            index = GRAPH_NODES.index(node)
        except ValueError:
            return None
        if index + 1 >= len(GRAPH_NODES):
            return "observe"
        return GRAPH_NODES[index + 1]

    def _load_checkpoint(self, checkpoint_path: Path) -> dict[str, Any]:
        if not checkpoint_path.exists():
            return {}
        try:
            payload = json.loads(checkpoint_path.read_text(encoding="utf-8") or "{}")
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _write_checkpoint(self, checkpoint_path: Path, payload: dict[str, Any]) -> None:
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_path.write_text(
            json.dumps(sanitize_agent_payload(payload), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _write_trace(self, trace_path: Path, trace: dict[str, Any]) -> None:
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace_path.write_text(
            json.dumps(sanitize_agent_payload(trace), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _add_trace_artifact(
        self,
        *,
        task_id: str,
        trace_path: Path,
        checkpoint_path: Path,
        planner_trace_path: Path,
    ) -> None:
        if self.artifact_repo is None or not hasattr(self.artifact_repo, "add_artifact"):
            return
        self.artifact_repo.add_artifact(
            task_id=task_id,
            artifact_type="agent_auto_workflow_trace",
            artifact_path=trace_path,
            metadata={"summary": "LangGraph dev 自动运行轨迹"},
        )
        self.artifact_repo.add_artifact(
            task_id=task_id,
            artifact_type="agent_langgraph_checkpoint",
            artifact_path=checkpoint_path,
            metadata={"summary": "LangGraph dev checkpoint"},
        )
        if planner_trace_path.exists():
            self.artifact_repo.add_artifact(
                task_id=task_id,
                artifact_type="agent_planner_trace",
                artifact_path=planner_trace_path,
                metadata={"summary": "Planner 结构化决策轨迹"},
            )
