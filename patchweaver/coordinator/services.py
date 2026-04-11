"""任务编排相关 service。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from patchweaver.context.bootstrap_registry import BootstrapRegistry
from patchweaver.harness.attempt_engine import AttemptEngine
from patchweaver.harness.dispatch_policy import dispatch_mode
from patchweaver.models.constraint import ConstraintReport
from patchweaver.models.context import BootstrapManifest, ContextBundle
from patchweaver.models.evidence import EvidenceBundle, EvidenceSpan
from patchweaver.models.semantic import SemanticCard
from patchweaver.models.task import TaskContext

ModelT = TypeVar("ModelT", bound=BaseModel)


@dataclass(slots=True)
class TaskRunnerServices:
    """收拢主流程运行时依赖。"""

    runtime: Any
    build_config: Any
    prompts_config: Any
    task_repo: Any
    attempt_repo: Any
    artifact_repo: Any
    workspace_guard: Any
    retriever: Any
    patch_normalizer: Any
    semantic_analyzer: Any
    constraint_diagnoser: Any
    context_retriever: Any
    context_budgeter: Any
    context_assembler: Any
    bootstrap_registry: BootstrapRegistry
    prompt_compiler: Any
    skill_router: Any
    schema_guard: Any
    policy_guard: Any
    planner: Any
    rewriter: Any
    builder: Any
    failure_classifier: Any
    validator: Any
    harness: Any
    trace_writer: Any
    json_writer: Any
    md_writer: Any
    report_builder: Any


class CoordinatorSupport:
    """为各阶段 service 提供共享依赖和辅助方法。"""

    def __init__(self, services: TaskRunnerServices) -> None:
        """把共享依赖绑定到实例上，方便阶段 service 直接使用。"""

        self.services = services
        self.runtime = services.runtime
        self.build_config = services.build_config
        self.prompts_config = services.prompts_config
        self.task_repo = services.task_repo
        self.attempt_repo = services.attempt_repo
        self.artifact_repo = services.artifact_repo
        self.workspace_guard = services.workspace_guard
        self.retriever = services.retriever
        self.patch_normalizer = services.patch_normalizer
        self.semantic_analyzer = services.semantic_analyzer
        self.constraint_diagnoser = services.constraint_diagnoser
        self.context_retriever = services.context_retriever
        self.context_budgeter = services.context_budgeter
        self.context_assembler = services.context_assembler
        self.bootstrap_registry = services.bootstrap_registry
        self.prompt_compiler = services.prompt_compiler
        self.skill_router = services.skill_router
        self.schema_guard = services.schema_guard
        self.policy_guard = services.policy_guard
        self.planner = services.planner
        self.rewriter = services.rewriter
        self.builder = services.builder
        self.failure_classifier = services.failure_classifier
        self.validator = services.validator
        self.harness = services.harness
        self.trace_writer = services.trace_writer
        self.json_writer = services.json_writer
        self.md_writer = services.md_writer
        self.report_builder = services.report_builder

    def build_bootstrap_manifest(self) -> BootstrapManifest:
        """按当前配置整理 bootstrap 片段。"""

        fragment_roots = [
            self.runtime.project_root / raw_dir for raw_dir in self.prompts_config.bootstrap_fragment_dirs
        ]
        return self.bootstrap_registry.build_manifest(fragment_roots)

    def materialize_stage_packet(
        self,
        *,
        stage_name: str,
        schema_name: str,
        context_bundle: ContextBundle,
        bootstrap_manifest: BootstrapManifest,
        base_dir: Path,
    ) -> dict[str, Any]:
        """为单个阶段输出 route 和 prompt 产物。"""

        require_write = dispatch_mode(stage_name) == "write-exclusive"
        self.policy_guard.ensure_stage_allowed(stage_name, require_write=require_write)

        route = self.skill_router.route(stage_name)
        self.schema_guard.require_value(route.selected_skill, label=f"{stage_name} 路由结果")
        prompt_packet = self.prompt_compiler.compile(
            stage_name=stage_name,
            context_bundle=context_bundle,
            bootstrap_manifest=bootstrap_manifest,
            schema_name=schema_name,
        )
        self.schema_guard.require_value(prompt_packet.prompt_sections, label=f"{stage_name} 提示包")

        route_path = self.json_writer.write_model(route, base_dir / "route" / f"{stage_name}_skill_route.json")
        prompt_path = self.json_writer.write_model(prompt_packet, base_dir / "prompt" / f"{stage_name}_prompt_packet.json")
        return {
            "route": route,
            "prompt_packet": prompt_packet,
            "route_path": route_path,
            "prompt_path": prompt_path,
        }

    def require_task(self, task_id: str) -> TaskContext:
        """读取任务，不存在时直接报错。"""

        task = self.task_repo.get_task(task_id)
        if task is None:
            raise ValueError(f"未找到任务：{task_id}")
        return task

    def load_model(self, path: Path, model_type: type[ModelT]) -> ModelT:
        """按模型类型读取本地 JSON 文件。"""

        return model_type.model_validate_json(path.read_text(encoding="utf-8"))

    def build_evidence_bundle(self, *, source_paths: list[Path | None], bundle_tag: str) -> EvidenceBundle:
        """根据已有产物生成一份最小证据包。"""

        spans: list[EvidenceSpan] = []
        evidence_ids: list[str] = []
        for index, source_path in enumerate(source_paths, start=1):
            if source_path is None or not source_path.exists():
                continue
            evidence_id = f"{bundle_tag}-{index:02d}"
            evidence_ids.append(evidence_id)
            excerpt = source_path.read_text(encoding="utf-8")[:400]
            spans.append(
                EvidenceSpan(
                    evidence_id=evidence_id,
                    source_type=source_path.suffix.lstrip(".") or "text",
                    source_path=str(source_path),
                    excerpt=excerpt,
                    start_line=1,
                    end_line=20,
                    score=1.0,
                )
            )
        return EvidenceBundle(evidence_ids=evidence_ids, spans=spans, memory_hits=[])

    def assemble_context(self, *, stage_name: str, evidence_bundle: EvidenceBundle) -> ContextBundle:
        """按阶段预算生成上下文包。"""

        selected = self.context_retriever.select(evidence_bundle)
        context_bundle = self.context_assembler.assemble(selected)
        budget = self.context_budgeter.budget_for(stage_name)

        notes = list(context_bundle.notes)
        notes.append(f"阶段预算上限: {budget['token_limit']}")
        notes.append(f"调度模式: {dispatch_mode(stage_name)}")
        if context_bundle.token_cost > budget["token_limit"]:
            notes.append("当前上下文已超过默认预算，后续应补充裁剪策略。")
        return context_bundle.model_copy(update={"notes": notes})


class AnalysisService(CoordinatorSupport):
    """负责分析阶段的任务编排。"""

    def run(self, task_id: str) -> dict[str, Any]:
        """执行最小分析链路。"""

        task = self.require_task(task_id)
        task_dir = self.workspace_guard.create_task_workspace(task)

        # 分析阶段先把原始 patch 和规范化 patch 固定下来，后续阶段都复用这些输入。
        raw_patch_path = task_dir / "input" / "raw_patch.patch"
        raw_patch_path.write_text(self.retriever.render_placeholder_patch(task.cve_id), encoding="utf-8")

        bundle = self.retriever.fetch_patch_bundle(task=task, raw_patch_path=raw_patch_path)
        normalized_patch_path = task_dir / "normalized" / "normalized.patch"
        self.patch_normalizer.normalize(raw_patch_path, normalized_patch_path)
        bundle.normalized_patch_path = normalized_patch_path

        semantic_card = self.semantic_analyzer.analyze(task, bundle)
        constraint_report = self.constraint_diagnoser.diagnose(bundle)
        bootstrap_manifest = self.build_bootstrap_manifest()

        patch_bundle_path = self.json_writer.write_model(bundle, task_dir / "input" / "patch_bundle.json")
        semantic_card_path = self.json_writer.write_model(semantic_card, task_dir / "analysis" / "semantic_card.json")
        constraint_report_path = self.json_writer.write_model(constraint_report, task_dir / "analysis" / "constraint_report.json")
        bootstrap_manifest_path = self.json_writer.write_model(
            bootstrap_manifest,
            task_dir / "analysis" / "bootstrap" / "bootstrap_manifest.json",
        )

        analysis_sources = [patch_bundle_path, semantic_card_path, constraint_report_path]
        evidence_bundle = self.build_evidence_bundle(source_paths=analysis_sources, bundle_tag="ANL")
        context_bundle = self.assemble_context(stage_name="constraint_diagnosis", evidence_bundle=evidence_bundle)
        evidence_bundle_path = self.json_writer.write_model(
            evidence_bundle,
            task_dir / "analysis" / "context" / "evidence_bundle.json",
        )
        context_bundle_path = self.json_writer.write_model(
            context_bundle,
            task_dir / "analysis" / "context" / "context_bundle.json",
        )

        retrieval_packet = self.materialize_stage_packet(
            stage_name="retrieval",
            schema_name="PatchBundle",
            context_bundle=context_bundle,
            bootstrap_manifest=bootstrap_manifest,
            base_dir=task_dir / "analysis",
        )
        semantic_packet = self.materialize_stage_packet(
            stage_name="semantic_card",
            schema_name="SemanticCard",
            context_bundle=context_bundle,
            bootstrap_manifest=bootstrap_manifest,
            base_dir=task_dir / "analysis",
        )
        constraint_packet = self.materialize_stage_packet(
            stage_name="constraint_diagnosis",
            schema_name="ConstraintReport",
            context_bundle=context_bundle,
            bootstrap_manifest=bootstrap_manifest,
            base_dir=task_dir / "analysis",
        )

        analysis_trace = self.harness.start_trace(
            trace_id=f"{task.task_id}-analysis",
            task_id=task.task_id,
            attempt_no=0,
        )
        analysis_trace = self.harness.record_stage(
            analysis_trace,
            from_stage="created",
            to_stage="retrieval",
            reason="开始整理 patch 来源与修复链路。",
        )
        analysis_trace = self.harness.attach_stage_route(analysis_trace, retrieval_packet["route"])
        analysis_trace = self.harness.attach_dispatch_mode(
            analysis_trace,
            stage_name="retrieval",
            mode=dispatch_mode("retrieval"),
        )
        analysis_trace = self.harness.record_stage(
            analysis_trace,
            from_stage="retrieval",
            to_stage="semantic_card",
            reason="进入语义卡片整理阶段。",
        )
        analysis_trace = self.harness.attach_stage_route(analysis_trace, semantic_packet["route"])
        analysis_trace = self.harness.attach_dispatch_mode(
            analysis_trace,
            stage_name="semantic_card",
            mode=dispatch_mode("semantic_card"),
        )
        analysis_trace = self.harness.record_stage(
            analysis_trace,
            from_stage="semantic_card",
            to_stage="constraint_diagnosis",
            reason="进入热补丁约束分析阶段。",
        )
        analysis_trace = self.harness.attach_stage_route(analysis_trace, constraint_packet["route"])
        analysis_trace = self.harness.attach_dispatch_mode(
            analysis_trace,
            stage_name="constraint_diagnosis",
            mode=dispatch_mode("constraint_diagnosis"),
        )
        analysis_trace = self.harness.attach_artifact(
            analysis_trace,
            artifact_type="patch_bundle",
            artifact_path=patch_bundle_path,
            summary="分析输入补丁包",
        )
        analysis_trace = self.harness.attach_artifact(
            analysis_trace,
            artifact_type="semantic_card",
            artifact_path=semantic_card_path,
            summary="语义分析结果",
        )
        analysis_trace = self.harness.attach_artifact(
            analysis_trace,
            artifact_type="constraint_report",
            artifact_path=constraint_report_path,
            summary="约束诊断结果",
        )
        analysis_trace_path = self.trace_writer.write(analysis_trace, task_dir / "analysis" / "trace" / "analysis_trace.json")

        self.task_repo.save_patch_bundle(bundle)
        self.task_repo.update_task_status(task.task_id, status="analyzed", current_attempt=0)

        for artifact_type, artifact_path in [
            ("raw_patch", raw_patch_path),
            ("normalized_patch", normalized_patch_path),
            ("patch_bundle", patch_bundle_path),
            ("semantic_card", semantic_card_path),
            ("constraint_report", constraint_report_path),
            ("analysis_bootstrap_manifest", bootstrap_manifest_path),
            ("analysis_evidence_bundle", evidence_bundle_path),
            ("analysis_context_bundle", context_bundle_path),
            ("retrieval_skill_route", retrieval_packet["route_path"]),
            ("retrieval_prompt_packet", retrieval_packet["prompt_path"]),
            ("semantic_card_skill_route", semantic_packet["route_path"]),
            ("semantic_card_prompt_packet", semantic_packet["prompt_path"]),
            ("constraint_skill_route", constraint_packet["route_path"]),
            ("constraint_prompt_packet", constraint_packet["prompt_path"]),
            ("analysis_trace", analysis_trace_path),
        ]:
            self.artifact_repo.add_artifact(task_id=task.task_id, artifact_type=artifact_type, artifact_path=artifact_path)

        return {
            "command": "analyze",
            "task_id": task.task_id,
            "patch_bundle_path": str(patch_bundle_path),
            "semantic_card_path": str(semantic_card_path),
            "constraint_report_path": str(constraint_report_path),
            "bootstrap_manifest_path": str(bootstrap_manifest_path),
            "analysis_trace_path": str(analysis_trace_path),
            "status": "ok",
        }


class AttemptExecutionService(CoordinatorSupport):
    """负责单轮尝试的执行与落盘。"""

    def run(self, task_id: str) -> dict[str, Any]:
        """执行最小单轮尝试链路。"""

        task = self.require_task(task_id)
        task_dir = self.workspace_guard.create_task_workspace(task)
        if not (task_dir / "analysis" / "semantic_card.json").exists():
            AnalysisService(self.services).run(task_id)

        attempt_no = self.attempt_repo.next_attempt_no(task_id)
        attempt_dir = self.workspace_guard.create_attempt_workspace(task_dir, attempt_no)

        semantic_card = self.load_model(task_dir / "analysis" / "semantic_card.json", SemanticCard)
        constraint_report = self.load_model(task_dir / "analysis" / "constraint_report.json", ConstraintReport)
        bootstrap_manifest = self.build_bootstrap_manifest()

        rewrite_evidence = self.build_evidence_bundle(
            source_paths=[
                task_dir / "input" / "patch_bundle.json",
                task_dir / "analysis" / "semantic_card.json",
                task_dir / "analysis" / "constraint_report.json",
            ],
            bundle_tag=f"RW{attempt_no:03d}",
        )
        rewrite_context = self.assemble_context(stage_name="rewrite_recipe", evidence_bundle=rewrite_evidence)
        rewrite_evidence_path = self.json_writer.write_model(rewrite_evidence, attempt_dir / "context" / "evidence_bundle.json")
        rewrite_context_path = self.json_writer.write_model(rewrite_context, attempt_dir / "context" / "context_bundle.json")
        rewrite_bootstrap_path = self.json_writer.write_model(bootstrap_manifest, attempt_dir / "prompt" / "bootstrap_manifest.json")
        rewrite_packet = self.materialize_stage_packet(
            stage_name="rewrite_recipe",
            schema_name="RewritePlan",
            context_bundle=rewrite_context,
            bootstrap_manifest=bootstrap_manifest,
            base_dir=attempt_dir,
        )

        plan = self.planner.plan(task_id=task.task_id, semantic_card=semantic_card, constraint_report=constraint_report)
        rewrite_plan_path = self.json_writer.write_model(plan, attempt_dir / "rewrite" / "rewrite_plan.json")
        rewritten_patch_path = self.rewriter.render_placeholder_patch(plan, attempt_dir / "rewrite" / "rewritten.patch")
        rewrite_meta = self.rewriter.write_rewrite_metadata(plan, attempt_dir / "rewrite")

        attempt_record, build_log = self.builder.execute_build(
            task=task,
            attempt_no=attempt_no,
            plan=plan,
            rewritten_patch_path=rewritten_patch_path,
            build_log_path=attempt_dir / "logs" / "build.log",
        )
        self.attempt_repo.create_attempt(attempt_record)
        self.attempt_repo.save_evidence_spans(task.task_id, attempt_record.attempt_id, rewrite_evidence.spans)

        failure_record = self.failure_classifier.classify_build_log(
            task_id=task.task_id,
            attempt_id=attempt_record.attempt_id,
            build_log=build_log,
        )
        self.attempt_repo.save_failure_record(failure_record)
        failure_record_path = self.json_writer.write_model(failure_record, attempt_dir / "logs" / "failure_record.json")

        validation_report = self.validator.empty_report()
        validate_log_path = attempt_dir / "logs" / "validate.log"
        validate_log_path.write_text("当前轮未进入真实加载验证。\n", encoding="utf-8")
        self.attempt_repo.save_validation_report(attempt_record.attempt_id, validation_report)
        validation_report_path = self.json_writer.write_model(validation_report, attempt_dir / "artifacts" / "validation_report.json")

        failure_packet: dict[str, Any] | None = None
        failure_context_path: Path | None = None
        failure_evidence_path: Path | None = None
        if attempt_record.status == "failed":
            failure_evidence = self.build_evidence_bundle(
                source_paths=[rewrite_plan_path, failure_record_path, attempt_record.build_log_path],
                bundle_tag=f"FA{attempt_no:03d}",
            )
            failure_context = self.assemble_context(stage_name="failure_analysis", evidence_bundle=failure_evidence)
            failure_evidence_path = self.json_writer.write_model(
                failure_evidence,
                attempt_dir / "context" / "failure_analysis_evidence_bundle.json",
            )
            failure_context_path = self.json_writer.write_model(
                failure_context,
                attempt_dir / "context" / "failure_analysis_context_bundle.json",
            )
            self.attempt_repo.save_evidence_spans(task.task_id, attempt_record.attempt_id, failure_evidence.spans)
            failure_packet = self.materialize_stage_packet(
                stage_name="failure_analysis",
                schema_name="FailureRecord",
                context_bundle=failure_context,
                bootstrap_manifest=bootstrap_manifest,
                base_dir=attempt_dir,
            )

        validation_evidence = self.build_evidence_bundle(
            source_paths=[rewrite_plan_path, failure_record_path, validation_report_path],
            bundle_tag=f"VD{attempt_no:03d}",
        )
        validation_context = self.assemble_context(stage_name="validation", evidence_bundle=validation_evidence)
        validation_evidence_path = self.json_writer.write_model(
            validation_evidence,
            attempt_dir / "context" / "validation_evidence_bundle.json",
        )
        validation_context_path = self.json_writer.write_model(
            validation_context,
            attempt_dir / "context" / "validation_context_bundle.json",
        )
        self.attempt_repo.save_evidence_spans(task.task_id, attempt_record.attempt_id, validation_evidence.spans)
        validation_packet = self.materialize_stage_packet(
            stage_name="validation",
            schema_name="ValidationReport",
            context_bundle=validation_context,
            bootstrap_manifest=bootstrap_manifest,
            base_dir=attempt_dir,
        )

        state = AttemptEngine().create_initial_state(task_id=task.task_id, max_attempts=task.max_attempts)
        state = state.model_copy(
            update={
                "attempt_no": attempt_no,
                "stage": "validation",
                "termination_reason": failure_record.failure_type if attempt_record.status == "failed" else "构建完成",
            }
        )
        self.attempt_repo.save_attempt_state(state)
        state_path = self.json_writer.write_model(state, attempt_dir / "attempt_state.json")

        trace = self.harness.start_trace(
            trace_id=f"{task.task_id}-trace-{attempt_no:03d}",
            task_id=task.task_id,
            attempt_no=attempt_no,
        )
        trace = self.harness.record_stage(
            trace,
            from_stage="analyzed",
            to_stage="rewrite_recipe",
            reason="进入改写规划与补丁生成阶段。",
        )
        trace = self.harness.attach_stage_route(trace, rewrite_packet["route"])
        trace = self.harness.attach_dispatch_mode(
            trace,
            stage_name="rewrite_recipe",
            mode=dispatch_mode("rewrite_recipe"),
        )
        trace = self.harness.record_stage(
            trace,
            from_stage="rewrite_recipe",
            to_stage="build",
            reason="改写产物已落盘，准备进入构建阶段。",
        )
        trace = self.harness.attach_dispatch_mode(trace, stage_name="build", mode=dispatch_mode("build"))
        trace = self.harness.record_tool_call(
            trace,
            tool_name="build",
            action=self.build_config.kpatch_build_cmd,
            status=attempt_record.status,
            detail=build_log,
        )
        if failure_packet is not None:
            trace = self.harness.record_stage(
                trace,
                from_stage="build",
                to_stage="failure_analysis",
                reason="构建未通过，转入失败归因阶段。",
            )
            trace = self.harness.attach_stage_route(trace, failure_packet["route"])
            trace = self.harness.attach_dispatch_mode(
                trace,
                stage_name="failure_analysis",
                mode=dispatch_mode("failure_analysis"),
            )
            previous_stage = "failure_analysis"
        else:
            previous_stage = "build"
        trace = self.harness.record_stage(
            trace,
            from_stage=previous_stage,
            to_stage="validation",
            reason="整理验证输入并输出验证结果。",
        )
        trace = self.harness.attach_stage_route(trace, validation_packet["route"])
        trace = self.harness.attach_dispatch_mode(
            trace,
            stage_name="validation",
            mode=dispatch_mode("validation"),
        )
        for artifact_type, artifact_path, summary in [
            ("rewrite_plan", rewrite_plan_path, "候选改写规划"),
            ("rewritten_patch", rewritten_patch_path, "单轮改写结果"),
            ("failure_record", failure_record_path, "构建失败归因"),
            ("validation_report", validation_report_path, "验证结果摘要"),
        ]:
            trace = self.harness.attach_artifact(
                trace,
                artifact_type=artifact_type,
                artifact_path=artifact_path,
                summary=summary,
            )
        trace_path = self.trace_writer.write(trace, attempt_dir / "trace" / "harness_trace.json")
        self.attempt_repo.save_harness_trace(trace, trace_path=trace_path)

        for artifact_type, artifact_path in [
            ("rewrite_bootstrap_manifest", rewrite_bootstrap_path),
            ("rewrite_evidence_bundle", rewrite_evidence_path),
            ("rewrite_context_bundle", rewrite_context_path),
            ("rewrite_skill_route", rewrite_packet["route_path"]),
            ("rewrite_prompt_packet", rewrite_packet["prompt_path"]),
            ("rewrite_plan", rewrite_plan_path),
            ("rewritten_patch", rewritten_patch_path),
            ("rewrite_reason", rewrite_meta["rewrite_reason"]),
            ("transformation_trace", rewrite_meta["transformation_trace"]),
            ("build_log", attempt_record.build_log_path),
            ("failure_record", failure_record_path),
            ("validate_log", validate_log_path),
            ("validation_report", validation_report_path),
            ("validation_evidence_bundle", validation_evidence_path),
            ("validation_context_bundle", validation_context_path),
            ("validation_skill_route", validation_packet["route_path"]),
            ("validation_prompt_packet", validation_packet["prompt_path"]),
            ("attempt_state", state_path),
            ("harness_trace", trace_path),
        ]:
            self.artifact_repo.add_artifact(
                task_id=task.task_id,
                artifact_type=artifact_type,
                artifact_path=artifact_path,
                attempt_id=attempt_record.attempt_id,
            )

        if failure_packet is not None and failure_context_path is not None and failure_evidence_path is not None:
            for artifact_type, artifact_path in [
                ("failure_analysis_evidence_bundle", failure_evidence_path),
                ("failure_analysis_context_bundle", failure_context_path),
                ("failure_analysis_skill_route", failure_packet["route_path"]),
                ("failure_analysis_prompt_packet", failure_packet["prompt_path"]),
            ]:
                self.artifact_repo.add_artifact(
                    task_id=task.task_id,
                    artifact_type=artifact_type,
                    artifact_path=artifact_path,
                    attempt_id=attempt_record.attempt_id,
                )

        final_status = "failed" if attempt_record.status == "failed" else attempt_record.status
        self.task_repo.update_task_status(task.task_id, status=final_status, current_attempt=attempt_no)
        return {
            "command": "run",
            "task_id": task.task_id,
            "attempt_id": attempt_record.attempt_id,
            "attempt_no": attempt_no,
            "status": attempt_record.status,
            "failure_type": attempt_record.failure_type,
            "build_log_path": str(attempt_record.build_log_path) if attempt_record.build_log_path else None,
            "trace_path": str(trace_path),
            "failure_record_path": str(failure_record_path),
        }


class ReportService(CoordinatorSupport):
    """负责最终报告阶段的任务编排。"""

    def run(self, task_id: str) -> dict[str, Any]:
        """生成最终 JSON 和 Markdown 报告。"""

        task = self.require_task(task_id)
        task_dir = self.workspace_guard.create_task_workspace(task)
        attempts = self.attempt_repo.list_attempts(task_id)
        artifacts = self.artifact_repo.list_artifacts(task_id)
        bootstrap_manifest = self.build_bootstrap_manifest()

        report_sources = [
            task_dir / "analysis" / "semantic_card.json",
            task_dir / "analysis" / "constraint_report.json",
        ]
        if attempts:
            latest_attempt_dir = task_dir / "attempts" / f"{attempts[-1].attempt_no:03d}"
            report_sources.extend(
                [
                    latest_attempt_dir / "rewrite" / "rewrite_plan.json",
                    latest_attempt_dir / "logs" / "failure_record.json",
                ]
            )
        report_evidence = self.build_evidence_bundle(source_paths=report_sources, bundle_tag="RPT")
        report_context = self.assemble_context(stage_name="reporting", evidence_bundle=report_evidence)
        report_evidence_path = self.json_writer.write_model(
            report_evidence,
            task_dir / "reports" / "context" / "evidence_bundle.json",
        )
        report_context_path = self.json_writer.write_model(
            report_context,
            task_dir / "reports" / "context" / "context_bundle.json",
        )
        report_bootstrap_path = self.json_writer.write_model(
            bootstrap_manifest,
            task_dir / "reports" / "prompt" / "bootstrap_manifest.json",
        )
        report_packet = self.materialize_stage_packet(
            stage_name="reporting",
            schema_name="FinalReport",
            context_bundle=report_context,
            bootstrap_manifest=bootstrap_manifest,
            base_dir=task_dir / "reports",
        )

        explanations = [
            f"当前共执行 {len(attempts)} 轮尝试。",
            "分析、归因和报告阶段按只读路径整理证据，改写与构建阶段走写入独占路径。",
        ]
        if attempts:
            latest = attempts[-1]
            explanations.append(f"最近一轮结果为 {latest.status}，失败类型为 {latest.failure_type or '无'}。")

        report = self.report_builder.build_report(
            task=task,
            attempts=attempts,
            artifacts=artifacts,
            explanations=explanations,
        )

        json_path = self.json_writer.write_model(report, task_dir / "reports" / "report.json")
        md_path = self.md_writer.write_report(report, task_dir / "reports" / "report.md")

        for artifact_type, artifact_path in [
            ("reporting_evidence_bundle", report_evidence_path),
            ("reporting_context_bundle", report_context_path),
            ("reporting_bootstrap_manifest", report_bootstrap_path),
            ("reporting_skill_route", report_packet["route_path"]),
            ("reporting_prompt_packet", report_packet["prompt_path"]),
            ("final_report_json", json_path),
            ("final_report_md", md_path),
        ]:
            self.artifact_repo.add_artifact(task_id=task.task_id, artifact_type=artifact_type, artifact_path=artifact_path)

        return {
            "command": "report",
            "task_id": task.task_id,
            "report_json": str(json_path),
            "report_md": str(md_path),
            "status": "ok",
        }


class ReplayService(CoordinatorSupport):
    """负责回放阶段的任务编排。"""

    def run(self, task_id: str) -> dict[str, Any]:
        """输出任务最近一轮的回放信息。"""

        task = self.require_task(task_id)
        task_dir = self.workspace_guard.create_task_workspace(task)
        latest_trace = self.attempt_repo.latest_trace_summary(task_id)
        attempts = self.attempt_repo.list_attempts(task_id)
        latest_attempt = attempts[-1] if attempts else None
        report_path = task_dir / "reports" / "report.json"

        stage_routes = {}
        dispatch_modes = {}
        if latest_trace:
            summary = latest_trace.get("summary") or {}
            extras = summary.get("extras") or {}
            stage_routes = extras.get("stage_routes") or {}
            dispatch_modes = extras.get("dispatch_modes") or {}

        replay_files: list[str] = []
        if latest_attempt is not None:
            latest_attempt_dir = task_dir / "attempts" / f"{latest_attempt.attempt_no:03d}"
            for candidate in [
                latest_attempt_dir / "prompt" / "rewrite_recipe_prompt_packet.json",
                latest_attempt_dir / "logs" / "failure_record.json",
                latest_attempt_dir / "trace" / "harness_trace.json",
                latest_attempt_dir / "attempt_state.json",
            ]:
                if candidate.exists():
                    replay_files.append(str(candidate))

        return {
            "command": "replay",
            "task_id": task.task_id,
            "latest_attempt_id": latest_attempt.attempt_id if latest_attempt else None,
            "latest_attempt_status": latest_attempt.status if latest_attempt else None,
            "trace_path": latest_trace["trace_path"] if latest_trace else None,
            "report_path": str(report_path) if report_path.exists() else None,
            "stage_routes": stage_routes,
            "dispatch_modes": dispatch_modes,
            "replay_files": replay_files,
            "status": "ok",
        }
