"""任务主链编排入口"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from patchweaver.agent.actions import AgentActionName
from patchweaver.agent.policy import DecisionPolicy
from patchweaver.agent.registry import AgentActionRegistry
from patchweaver.agent.state import AgentDecision, AgentObservation, reduce_observation
from patchweaver.agent.trace import append_agent_workflow_trace
from patchweaver.analyzer.constraint_service import ConstraintDiagnoser
from patchweaver.analyzer.semantic_enricher import SemanticCardEnricher
from patchweaver.analyzer.patch_normalizer import PatchNormalizer
from patchweaver.analyzer.semantic_service import SemanticAnalyzer
from patchweaver.builder.failure_classifier import FailureClassifier
from patchweaver.builder.orchestrator import BuildOrchestrator
from patchweaver.context.assembler import ContextAssembler
from patchweaver.context.bootstrap_registry import BootstrapRegistry
from patchweaver.context.budgeter import ContextBudgeter
from patchweaver.context.retriever import ContextRetriever
from patchweaver.harness.evaluator import Evaluator
from patchweaver.harness.failover_controller import FailoverController
from patchweaver.harness.replay import ReplayHarness
from patchweaver.harness.orchestrator import HarnessOrchestrator
from patchweaver.harness.policy_guard import PolicyGuard
from patchweaver.harness.schema_guard import SchemaGuard
from patchweaver.harness.trace_writer import TraceWriter
from patchweaver.harness.workspace_guard import WorkspaceGuard
from patchweaver.memory.dual_memory import DualMemory
from patchweaver.models.attempt import AttemptRecord, FailureRecord
from patchweaver.models.task import TaskContext
from patchweaver.models.validation import ValidationReport
from patchweaver.planner.joint_planner import JointPlanner
from patchweaver.prompting.compiler import PromptCompiler
from patchweaver.reporter.json_writer import JsonWriter
from patchweaver.reporter.md_writer import MdWriter
from patchweaver.reporter.report_builder import ReportBuilder
from patchweaver.rag.context_injector import RagContextInjector
from patchweaver.retriever.service import RetrieverService
from patchweaver.rewriter.executor import RewriteExecutor
from patchweaver.skills.router import SkillRouter
from patchweaver.storage.artifact_repo import ArtifactRepository
from patchweaver.storage.attempt_repo import AttemptRepository
from patchweaver.storage.task_repo import TaskRepository
from patchweaver.validator.validator import Validator

from patchweaver.coordinator.services import (
    AnalysisService,
    AttemptExecutionService,
    ReplayService,
    ReportService,
    TaskRunnerServices,
)


class TaskRunner:
    """负责暴露任务级主流程入口"""

    AGENT_RETRYABLE_FAILURES = {"kpatch_constraint"}

    def __init__(
        self,
        runtime: Any,
        build_config: Any,
        verify_config: Any,
        prompts_config: Any,
        skills_config: Any | None = None,
        models_config: Any | None = None,
        rag_config: Any | None = None,
    ) -> None:
        """绑定运行时配置，并装配各阶段 service"""

        prompt_profile = prompts_config.prompt_profiles.get(prompts_config.default_prompt_profile)
        enable_dedup = prompt_profile.suppress_duplicate_evidence if prompt_profile is not None else True
        track_token_cost = prompt_profile.track_token_cost if prompt_profile is not None else True
        services = TaskRunnerServices(
            runtime=runtime,
            build_config=build_config,
            prompts_config=prompts_config,
            task_repo=TaskRepository(runtime.database_path, runtime.project_root),
            attempt_repo=AttemptRepository(runtime.database_path, runtime.project_root),
            artifact_repo=ArtifactRepository(runtime.database_path, runtime.project_root),
            workspace_guard=WorkspaceGuard(runtime.workspace_root, runtime.project_root),
            retriever=RetrieverService(cache_dir=runtime.data_dir / "cache" / "source_fetch"),
            patch_normalizer=PatchNormalizer(),
            semantic_analyzer=SemanticAnalyzer(
                enricher=SemanticCardEnricher(
                    models_config=models_config,
                    project_root=runtime.project_root,
                ),
            ),
            constraint_diagnoser=ConstraintDiagnoser(),
            context_retriever=ContextRetriever(),
            context_budgeter=ContextBudgeter(),
            context_assembler=ContextAssembler(enable_dedup=enable_dedup, track_token_cost=track_token_cost),
            bootstrap_registry=BootstrapRegistry(),
            prompt_compiler=PromptCompiler(runtime.project_root),
            skill_router=SkillRouter(runtime.project_root, skills_config=skills_config),
            schema_guard=SchemaGuard(),
            policy_guard=PolicyGuard(),
            planner=JointPlanner(),
            rewriter=RewriteExecutor(runtime.project_root),
            builder=BuildOrchestrator(build_config),
            failure_classifier=FailureClassifier(),
            validator=Validator(
                verify_config=verify_config,
                build_config=build_config,
                project_root=runtime.project_root,
            ),
            dual_memory=DualMemory(runtime.data_dir / "memory"),
            harness=HarnessOrchestrator(),
            failover_controller=FailoverController(),
            evaluator=Evaluator(),
            replay_harness=ReplayHarness(runtime.project_root),
            trace_writer=TraceWriter(runtime.project_root),
            json_writer=JsonWriter(runtime.project_root),
            md_writer=MdWriter(),
            report_builder=ReportBuilder(runtime.project_root),
            rag_context_injector=RagContextInjector(rag_config),
        )

        self.services = services
        self.decision_policy = DecisionPolicy()
        self.analysis_service = AnalysisService(services)
        self.attempt_service = AttemptExecutionService(services)
        self.report_service = ReportService(services)
        self.replay_service = ReplayService(services)

    def build_action_registry(self) -> AgentActionRegistry:
        """Return the guarded Agent action registry for this runner."""

        return AgentActionRegistry(
            task_repo=self.services.task_repo,
            attempt_repo=self.services.attempt_repo,
            task_runner=self,
            policy_guard=self.services.policy_guard,
            artifact_repo=self.services.artifact_repo,
            project_root=self.services.runtime.project_root,
            enable_read_parallel=self.services.runtime.enable_read_parallel,
        )

    def analyze_task(self, task_id: str) -> dict[str, Any]:
        """执行分析阶段"""

        return self.analysis_service.run(task_id)

    def run_task(self, task_id: str) -> dict[str, Any]:
        """执行 Agent 尝试阶段"""

        terminal_payload = self._terminal_status_payload(task_id)
        if terminal_payload is not None:
            return terminal_payload

        exhausted_payload = self._max_attempts_exhausted_payload(task_id)
        if exhausted_payload is not None:
            return exhausted_payload

        attempt_results: list[dict[str, Any]] = []
        retry_decisions: list[dict[str, Any]] = []
        while True:
            payload = self.attempt_service.run(task_id)
            attempt_results.append(payload)

            retry_decision = self._retry_decision(task_id=task_id, latest_payload=payload)
            retry_decisions.append(retry_decision)
            if not retry_decision["retry"]:
                break

        final_payload = dict(attempt_results[-1])
        final_payload["attempts_executed"] = len(attempt_results)
        final_payload["attempt_results"] = attempt_results
        final_payload["agent_retry_decisions"] = retry_decisions
        return final_payload

    def _terminal_status_payload(self, task_id: str) -> dict[str, Any] | None:
        """阻止已进入终止策略的任务被重复 run 生成无意义 attempt。"""

        task = self.services.task_repo.get_task(task_id)
        attempts = self.services.attempt_repo.list_attempts(task_id)
        if task is None or not attempts:
            return None
        latest = attempts[-1]
        latest_payload = {
            "task_id": task_id,
            "attempt_id": getattr(latest, "attempt_id", f"{task_id}-A{getattr(latest, 'attempt_no', 1):03d}"),
            "attempt_no": getattr(latest, "attempt_no", len(attempts)),
            "status": getattr(latest, "status", None),
            "failure_type": getattr(latest, "failure_type", None),
            "build_exec_status": getattr(latest, "build_exec_status", None),
            "target_state": getattr(latest, "target_state", None),
            "build_log_path": str(getattr(latest, "build_log_path", "")) if getattr(latest, "build_log_path", None) else None,
        }
        if latest_payload["status"] in {"created", "running"}:
            return None

        observation_task = self._coerce_task_context(task_id=task_id, task=task, latest_payload=latest_payload)
        latest_attempt = self._latest_attempt_from_runtime(
            task_id=task_id,
            latest_payload=latest_payload,
            attempts=attempts,
        )
        failure_record = self._load_failure_record_for_attempt(
            task=observation_task,
            latest_attempt=latest_attempt,
            latest_payload=latest_payload,
        )
        validation_report = self._load_validation_report_for_attempt(
            task=observation_task,
            latest_attempt=latest_attempt,
        )
        observation = AgentObservation.from_runtime(
            task=observation_task,
            latest_attempt=latest_attempt,
            failure_record=failure_record,
            validation_report=validation_report,
            memory_hints=[],
        )
        policy = getattr(self, "decision_policy", DecisionPolicy())
        agent_decision = policy.decide(observation)
        if not agent_decision.terminal:
            return None
        reduction = reduce_observation(observation, agent_decision)
        if isinstance(task, TaskContext):
            runtime = getattr(getattr(self, "services", None), "runtime", None)
            append_agent_workflow_trace(
                task=task,
                observation=observation,
                decision=agent_decision,
                reduction=reduction,
                project_root=getattr(runtime, "project_root", None),
            )

        max_attempts = int(getattr(task, "max_attempts", observation.max_attempts) or observation.max_attempts)
        return {
            "command": "run",
            "task_id": task_id,
            "attempt_id": latest_attempt.attempt_id,
            "attempt_no": latest_attempt.attempt_no,
            "status": latest_attempt.status,
            "failure_type": failure_record.failure_type,
            "build_exec_status": latest_attempt.build_exec_status,
            "target_state": latest_attempt.target_state,
            "build_log_path": str(latest_attempt.build_log_path) if latest_attempt.build_log_path else None,
            "max_attempts": max_attempts,
            "terminal_stop": True,
            "attempts_executed": 0,
            "attempt_results": [],
            "agent_retry_decisions": [
                {
                    "attempt_no": latest_attempt.attempt_no,
                    "failure_type": failure_record.failure_type,
                    "retry": False,
                    "reason": agent_decision.reason,
                    "selected_action": agent_decision.selected_action.value,
                    "terminal": True,
                    "remaining_attempts": max(0, max_attempts - len(attempts)),
                }
            ],
        }

    def _max_attempts_exhausted_payload(self, task_id: str) -> dict[str, Any] | None:
        """在外部重复调用 run 时阻止突破任务尝试预算"""

        task = self.services.task_repo.get_task(task_id)
        if task is None:
            return None
        attempts = self.services.attempt_repo.list_attempts(task_id)
        max_attempts = max(1, int(task.max_attempts or 1))
        if len(attempts) < max_attempts:
            return None
        latest = attempts[-1] if attempts else None
        if latest is None:
            return None

        return {
            "command": "run",
            "task_id": task_id,
            "attempt_id": latest.attempt_id,
            "attempt_no": latest.attempt_no,
            "status": latest.status,
            "failure_type": latest.failure_type,
            "build_exec_status": latest.build_exec_status,
            "target_state": latest.target_state,
            "build_log_path": str(latest.build_log_path) if latest.build_log_path else None,
            "max_attempts": max_attempts,
            "max_attempts_exhausted": True,
            "attempts_executed": 0,
            "attempt_results": [],
            "agent_retry_decisions": [
                {
                    "attempt_no": latest.attempt_no,
                    "failure_type": latest.failure_type,
                    "retry": False,
                    "reason": "已达到任务最大尝试次数",
                    "remaining_attempts": 0,
                }
            ],
        }

    def _retry_decision(self, *, task_id: str, latest_payload: dict[str, Any]) -> dict[str, Any]:
        """判断当前失败是否应由 Agent 进入下一轮"""

        task = self.services.task_repo.get_task(task_id)
        attempts = self.services.attempt_repo.list_attempts(task_id)
        max_attempts = task.max_attempts if task is not None else 1
        failure_type = latest_payload.get("failure_type")
        status = latest_payload.get("status")

        decision: dict[str, Any] = {
            "attempt_no": latest_payload.get("attempt_no"),
            "failure_type": failure_type,
            "retry": False,
            "reason": "当前结果不满足 Agent 自动重试条件",
            "remaining_attempts": max(0, max_attempts - len(attempts)),
        }
        if status in {"built", "target_state"}:
            decision["reason"] = "当前状态已到终止态，不进入下一轮"
            decision["selected_action"] = "report"
            return decision

        observation_task = self._coerce_task_context(task_id=task_id, task=task, latest_payload=latest_payload)
        latest_attempt = self._latest_attempt_from_runtime(
            task_id=task_id,
            latest_payload=latest_payload,
            attempts=attempts,
        )
        failure_record = self._load_failure_record_for_attempt(
            task=observation_task,
            latest_attempt=latest_attempt,
            latest_payload=latest_payload,
        )
        validation_report = self._load_validation_report_for_attempt(
            task=observation_task,
            latest_attempt=latest_attempt,
        )
        observation = AgentObservation.from_runtime(
            task=observation_task,
            latest_attempt=latest_attempt,
            failure_record=failure_record,
            validation_report=validation_report,
            memory_hints=[],
        )
        policy = getattr(self, "decision_policy", DecisionPolicy())
        agent_decision = policy.decide(observation)
        if len(attempts) >= max_attempts and agent_decision.retry:
            agent_decision = AgentDecision(
                selected_action=AgentActionName.STOP_MANUAL_REVIEW,
                reason=f"已达到任务最大尝试次数，不能执行下一轮；原策略建议：{agent_decision.reason}",
                evidence_refs=list(agent_decision.evidence_refs),
                risk=agent_decision.risk,
                terminal=True,
                retry=False,
                strategy_requirements=list(agent_decision.strategy_requirements),
                disabled_strategies=list(agent_decision.disabled_strategies),
            )
        reduction = reduce_observation(observation, agent_decision)
        if isinstance(task, TaskContext):
            runtime = getattr(getattr(self, "services", None), "runtime", None)
            append_agent_workflow_trace(
                task=task,
                observation=observation,
                decision=agent_decision,
                reduction=reduction,
                project_root=getattr(runtime, "project_root", None),
            )

        decision.update(
            {
                "retry": agent_decision.retry,
                "reason": agent_decision.reason,
                "selected_action": agent_decision.selected_action.value,
                "terminal": agent_decision.terminal,
                "risk": agent_decision.risk,
                "strategy_requirements": list(agent_decision.strategy_requirements),
                "disabled_strategies": list(agent_decision.disabled_strategies),
                "next_attempt_no": agent_decision.next_attempt_no,
            }
        )
        if agent_decision.terminal:
            decision["retry"] = False
        return decision

    def _coerce_task_context(self, *, task_id: str, task: Any, latest_payload: dict[str, Any]) -> TaskContext:
        """Build a TaskContext even when older tests use a minimal task stub."""

        if isinstance(task, TaskContext):
            return task
        return TaskContext(
            task_id=task_id,
            cve_id=str(getattr(task, "cve_id", latest_payload.get("cve_id") or "unknown")),
            target_kernel=str(getattr(task, "target_kernel", latest_payload.get("target_kernel") or "unknown")),
            status=str(getattr(task, "status", latest_payload.get("status") or "running")),
            max_attempts=int(getattr(task, "max_attempts", 1) or 1),
            current_attempt=int(getattr(task, "current_attempt", latest_payload.get("attempt_no") or 0) or 0),
            workspace_dir=Path(getattr(task, "workspace_dir", ".")).resolve(),
        )

    def _latest_attempt_from_runtime(
        self,
        *,
        task_id: str,
        latest_payload: dict[str, Any],
        attempts: list[Any],
    ) -> AttemptRecord:
        """Return a complete AttemptRecord for policy input."""

        latest = attempts[-1] if attempts else None
        if isinstance(latest, AttemptRecord):
            return latest
        attempt_no = int(latest_payload.get("attempt_no") or len(attempts) or 1)
        return AttemptRecord(
            task_id=task_id,
            attempt_no=attempt_no,
            attempt_id=str(latest_payload.get("attempt_id") or f"{task_id}-A{attempt_no:03d}"),
            status=str(latest_payload.get("status") or "failed"),
            failure_type=latest_payload.get("failure_type"),
            build_exec_status=latest_payload.get("build_exec_status"),
            target_state=latest_payload.get("target_state"),
            build_log_path=Path(str(latest_payload["build_log_path"])) if latest_payload.get("build_log_path") else None,
        )

    def _load_failure_record_for_attempt(
        self,
        *,
        task: TaskContext,
        latest_attempt: AttemptRecord,
        latest_payload: dict[str, Any],
    ) -> FailureRecord:
        """Load persisted failure details or synthesize minimum policy input."""

        candidates: list[Path] = []
        if latest_payload.get("failure_record_path"):
            candidates.append(Path(str(latest_payload["failure_record_path"])))
        candidates.append(
            task.workspace_dir / "attempts" / f"{latest_attempt.attempt_no:03d}" / "logs" / "failure_record.json"
        )
        if latest_attempt.attempt_no == 0:
            candidates.append(task.workspace_dir / "analysis" / "trace" / "failure_record.json")

        for path in candidates:
            if not path.exists():
                continue
            try:
                return FailureRecord.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                continue

        failure_type = str(latest_payload.get("failure_type") or latest_attempt.failure_type or "unknown")
        return FailureRecord(
            task_id=task.task_id,
            attempt_id=latest_attempt.attempt_id,
            stage_name="build",
            failure_type=failure_type,
            summary=f"{failure_type} failure",
            evidence=[],
        )

    def _load_validation_report_for_attempt(
        self,
        *,
        task: TaskContext,
        latest_attempt: AttemptRecord,
    ) -> ValidationReport | None:
        """Load the latest validation report when available."""

        path = task.workspace_dir / "attempts" / f"{latest_attempt.attempt_no:03d}" / "artifacts" / "validation_report.json"
        if not path.exists():
            return None
        try:
            return ValidationReport.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return None

    def build_report(self, task_id: str) -> dict[str, Any]:
        """生成最终报告"""

        return self.report_service.run(task_id)

    def replay_task(self, task_id: str) -> dict[str, Any]:
        """输出最近一轮回放信息"""

        return self.replay_service.run(task_id)
