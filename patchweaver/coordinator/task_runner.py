"""任务主链编排入口"""

from __future__ import annotations

from typing import Any

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
from patchweaver.planner.joint_planner import JointPlanner
from patchweaver.prompting.compiler import PromptCompiler
from patchweaver.reporter.json_writer import JsonWriter
from patchweaver.reporter.md_writer import MdWriter
from patchweaver.reporter.report_builder import ReportBuilder
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
        )

        self.services = services
        self.analysis_service = AnalysisService(services)
        self.attempt_service = AttemptExecutionService(services)
        self.report_service = ReportService(services)
        self.replay_service = ReplayService(services)

    def analyze_task(self, task_id: str) -> dict[str, Any]:
        """执行分析阶段"""

        return self.analysis_service.run(task_id)

    def run_task(self, task_id: str) -> dict[str, Any]:
        """执行 Agent 尝试阶段"""

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
            return decision
        if failure_type not in self.AGENT_RETRYABLE_FAILURES:
            decision["reason"] = f"{failure_type or 'unknown'} 不属于当前自动重试失败类型"
            return decision
        if len(attempts) >= max_attempts:
            decision["reason"] = "已达到任务最大尝试次数"
            return decision

        decision["retry"] = True
        decision["reason"] = "kpatch_constraint 可通过替代 Recipe 继续尝试"
        decision["next_attempt_no"] = len(attempts) + 1
        return decision

    def build_report(self, task_id: str) -> dict[str, Any]:
        """生成最终报告"""

        return self.report_service.run(task_id)

    def replay_task(self, task_id: str) -> dict[str, Any]:
        """输出最近一轮回放信息"""

        return self.replay_service.run(task_id)
