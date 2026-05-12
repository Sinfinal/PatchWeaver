"""Guarded Agent action registry."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field

from patchweaver.agent.actions import AgentActionName
from patchweaver.agent.state import AgentObservation, sanitize_agent_payload
from patchweaver.harness.policy_guard import PolicyGuard
from patchweaver.models.attempt import AttemptRecord, FailureRecord
from patchweaver.models.task import TaskContext
from patchweaver.models.validation import ValidationReport
from patchweaver.utils.path_policy import to_project_relative


@dataclass(slots=True)
class RegisteredAgentAction:
    """Action metadata plus executor."""

    name: AgentActionName
    stage_name: str
    require_write: bool
    handler: Callable[[str], dict[str, Any]]
    terminal: bool = False


class AgentActionResult(BaseModel):
    """Structured result returned by every guarded Agent action."""

    action_name: AgentActionName
    task_id: str
    status: str
    terminal: bool = False
    payload: dict[str, Any] = Field(default_factory=dict)
    observation: AgentObservation
    trace_path: str | None = None
    error: str | None = None


class AgentActionRegistry:
    """Expose only guarded task actions to the Agent layer."""

    def __init__(
        self,
        *,
        task_repo: Any,
        attempt_repo: Any,
        task_runner: Any,
        policy_guard: PolicyGuard,
        artifact_repo: Any | None = None,
        project_root: Path | None = None,
        enable_read_parallel: bool = True,
    ) -> None:
        self.task_repo = task_repo
        self.attempt_repo = attempt_repo
        self.task_runner = task_runner
        self.policy_guard = policy_guard
        self.artifact_repo = artifact_repo
        self.project_root = project_root.resolve() if project_root is not None else None
        self.enable_read_parallel = enable_read_parallel
        self.actions: dict[AgentActionName, RegisteredAgentAction] = {}
        self._register_defaults()

    def execute(
        self,
        action_name: AgentActionName | str,
        task_id: str,
        *,
        failure_record: FailureRecord | None = None,
        validation_report: ValidationReport | None = None,
        memory_hints: list[dict[str, Any]] | None = None,
        single_attempt: bool = False,
    ) -> AgentActionResult:
        """Execute a registered action and return a normalized observation."""

        normalized_name = self._normalize_action_name(action_name)
        action = self.actions.get(normalized_name)
        if action is None:
            raise ValueError(f"非法 Agent action：{action_name}")

        task = self._require_task(task_id)
        payload: dict[str, Any] = {}
        status = "ok"
        error: str | None = None
        terminal = action.terminal

        try:
            self.policy_guard.ensure_stage_allowed(
                action.stage_name,
                require_write=action.require_write,
                enable_read_parallel=self.enable_read_parallel,
            )
            if single_attempt and normalized_name == AgentActionName.RUN_TASK and hasattr(self.task_runner, "attempt_service"):
                payload = self.task_runner.attempt_service.run(task_id)
            else:
                payload = action.handler(task_id)
            if action.terminal:
                status = str(payload.get("status") or "stopped")
        except Exception as exc:
            status = "failed"
            error = str(exc)
            payload = {
                "status": "failed",
                "error": error,
                "action_name": normalized_name.value,
            }
            failure_record = failure_record or FailureRecord(
                task_id=task.task_id,
                attempt_id=f"{task.task_id}-agent-action",
                stage_name=action.stage_name,
                failure_type="action_failed",
                summary=error,
                diagnostic_details={"action_name": normalized_name.value},
            )
            if task.status == "created" and hasattr(self.task_repo, "update_task_status"):
                self.task_repo.update_task_status(task.task_id, status="failed", current_attempt=task.current_attempt)
                task = task.model_copy(update={"status": "failed"})

        latest_attempt = self._latest_attempt(task_id)
        observation = AgentObservation.from_runtime(
            task=task,
            latest_attempt=latest_attempt,
            failure_record=failure_record,
            validation_report=validation_report,
            memory_hints=memory_hints or [],
        )
        result = AgentActionResult(
            action_name=normalized_name,
            task_id=task.task_id,
            status=status,
            terminal=terminal,
            payload=sanitize_agent_payload(payload),
            observation=observation,
            error=error,
        )
        trace_path = self._append_action_trace(task=task, result=result)
        if self.artifact_repo is not None and hasattr(self.artifact_repo, "add_artifact"):
            self.artifact_repo.add_artifact(
                task_id=task.task_id,
                artifact_type="agent_action_trace",
                artifact_path=trace_path,
                metadata={"summary": "Agent 受控动作执行轨迹"},
            )
        return result.model_copy(update={"trace_path": to_project_relative(self.project_root, trace_path)})

    def register(self, action: RegisteredAgentAction) -> None:
        """Register or replace a guarded Agent action."""

        self.actions[action.name] = action

    def _register_defaults(self) -> None:
        self.register(
            RegisteredAgentAction(
                name=AgentActionName.GET_TASK_DETAIL,
                stage_name="retrieval",
                require_write=False,
                handler=self._get_task_detail,
            )
        )
        self.register(
            RegisteredAgentAction(
                name=AgentActionName.ANALYZE_TASK,
                stage_name="retrieval",
                require_write=False,
                handler=self.task_runner.analyze_task,
            )
        )
        self.register(
            RegisteredAgentAction(
                name=AgentActionName.RUN_TASK,
                stage_name="build",
                require_write=True,
                handler=self.task_runner.run_task,
            )
        )
        self.register(
            RegisteredAgentAction(
                name=AgentActionName.REPORT_TASK,
                stage_name="reporting",
                require_write=False,
                handler=self.task_runner.build_report,
            )
        )
        self.register(
            RegisteredAgentAction(
                name=AgentActionName.REPLAY_TASK,
                stage_name="reporting",
                require_write=False,
                handler=self.task_runner.replay_task,
            )
        )
        self.register(
            RegisteredAgentAction(
                name=AgentActionName.STOP_MANUAL_REVIEW,
                stage_name="failure_analysis",
                require_write=False,
                handler=self._stop_manual_review,
                terminal=True,
            )
        )

    def _normalize_action_name(self, action_name: AgentActionName | str) -> AgentActionName:
        if isinstance(action_name, AgentActionName):
            return action_name
        try:
            return AgentActionName(str(action_name))
        except ValueError as exc:
            raise ValueError(f"非法 Agent action：{action_name}") from exc

    def _require_task(self, task_id: str) -> TaskContext:
        task = self.task_repo.get_task(task_id)
        if task is None:
            raise ValueError(f"未找到任务：{task_id}")
        return task

    def _latest_attempt(self, task_id: str) -> AttemptRecord | None:
        if not hasattr(self.attempt_repo, "list_attempts"):
            return None
        attempts = self.attempt_repo.list_attempts(task_id)
        return attempts[-1] if attempts else None

    def _get_task_detail(self, task_id: str) -> dict[str, Any]:
        task = self._require_task(task_id)
        latest_attempt = self._latest_attempt(task_id)
        return {
            "status": "ok",
            "task": task.model_dump(mode="json"),
            "latest_attempt": latest_attempt.model_dump(mode="json") if latest_attempt is not None else None,
        }

    def _stop_manual_review(self, task_id: str) -> dict[str, Any]:
        return {
            "status": "stopped",
            "task_id": task_id,
            "reason": "AgentDecision 要求终止自动动作，等待人工复核",
        }

    def _append_action_trace(self, *, task: TaskContext, result: AgentActionResult) -> Path:
        trace_path = task.workspace_dir / "agent" / "agent_action_trace.json"
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        if trace_path.exists():
            try:
                payload = json.loads(trace_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload = {}
        else:
            payload = {}

        payload.setdefault("task_id", task.task_id)
        payload.setdefault("cve_id", task.cve_id)
        payload.setdefault("actions", [])
        payload["trace_path"] = to_project_relative(self.project_root, trace_path)
        payload["actions"].append(
            {
                "action_name": result.action_name.value,
                "status": result.status,
                "terminal": result.terminal,
                "error": result.error,
                "payload": result.payload,
                "observation": result.observation.model_dump(mode="json"),
            }
        )
        trace_path.write_text(
            json.dumps(sanitize_agent_payload(payload), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return trace_path
