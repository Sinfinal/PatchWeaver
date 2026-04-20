"""任务编排相关 service。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from patchweaver.context.bootstrap_registry import BootstrapRegistry
from patchweaver.harness.attempt_engine import AttemptEngine
from patchweaver.harness.dispatch_policy import dispatch_mode, is_write_stage
from patchweaver.models.attempt import BuildSummary, FailureRecord
from patchweaver.models.constraint import ConstraintReport
from patchweaver.models.context import BootstrapManifest, ContextBundle
from patchweaver.models.evidence import EvidenceBundle, EvidenceSpan
from patchweaver.models.patch import PatchBundle
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
    dual_memory: Any
    harness: Any
    failover_controller: Any
    evaluator: Any
    replay_harness: Any
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
        self.dual_memory = services.dual_memory
        self.harness = services.harness
        self.failover_controller = services.failover_controller
        self.evaluator = services.evaluator
        self.replay_harness = services.replay_harness
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

        require_write = is_write_stage(stage_name)
        self.policy_guard.ensure_stage_allowed(
            stage_name,
            require_write=require_write,
            enable_read_parallel=self.runtime.enable_read_parallel,
        )

        route = self.skill_router.route(stage_name)
        self.schema_guard.require_value(route.selected_skill, label=f"{stage_name} 路由结果")
        prompt_packet = self.prompt_compiler.compile(
            stage_name=stage_name,
            context_bundle=context_bundle,
            bootstrap_manifest=bootstrap_manifest,
            schema_name=schema_name,
            route=route,
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

    def dispatch_mode_for(self, stage_name: str) -> str:
        """按当前运行时开关返回阶段调度模式。"""

        return dispatch_mode(stage_name, enable_read_parallel=self.runtime.enable_read_parallel)

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

        prompt_profile = self.prompts_config.prompt_profiles.get(self.prompts_config.default_prompt_profile)
        max_evidence = prompt_profile.max_evidence_snippets if prompt_profile is not None else 8
        max_memory_hits = prompt_profile.max_memory_hits if prompt_profile is not None else 3
        memory_hits = self.dual_memory.recall(stage_name=stage_name, evidence_bundle=evidence_bundle, limit=max_memory_hits)
        enriched_bundle = evidence_bundle.model_copy(update={"memory_hits": memory_hits})
        selected = self.context_retriever.select(
            enriched_bundle,
            stage_name=stage_name,
            max_evidence=max_evidence,
            max_memory_hits=max_memory_hits,
        )
        context_bundle = self.context_assembler.assemble(selected)
        budget = self.context_budgeter.budget_for(stage_name)

        notes = list(context_bundle.notes)
        notes.append(f"阶段预算上限: {budget['token_limit']}")
        notes.append(f"调度模式: {self.dispatch_mode_for(stage_name)}")
        if memory_hits:
            notes.append(f"命中经验摘要: {len(memory_hits)}")
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
        bundle = self.retriever.fetch_patch_bundle(task=task, raw_patch_path=raw_patch_path)
        normalized_patch_path = task_dir / "normalized" / "normalized.patch"
        self.patch_normalizer.normalize(raw_patch_path, normalized_patch_path)
        bundle.normalized_patch_path = normalized_patch_path
        if not bundle.affected_files:
            bundle.affected_files = self.patch_normalizer.extract_affected_files(
                normalized_patch_path.read_text(encoding="utf-8")
            )

        semantic_card = self.semantic_analyzer.analyze(task, bundle)
        constraint_report = self.constraint_diagnoser.diagnose(bundle)
        bootstrap_manifest = self.build_bootstrap_manifest()

        patch_bundle_path = self.json_writer.write_model(bundle, task_dir / "input" / "patch_bundle.json")
        source_evidence_path = task_dir / "input" / "source_evidence.json"
        source_evidence_path.write_text(
            json.dumps([item.model_dump() for item in bundle.source_evidence], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
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
            mode=self.dispatch_mode_for("retrieval"),
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
            mode=self.dispatch_mode_for("semantic_card"),
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
            mode=self.dispatch_mode_for("constraint_diagnosis"),
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
            ("source_evidence", source_evidence_path),
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
            "source_evidence_path": str(source_evidence_path),
            "semantic_card_path": str(semantic_card_path),
            "constraint_report_path": str(constraint_report_path),
            "bootstrap_manifest_path": str(bootstrap_manifest_path),
            "analysis_trace_path": str(analysis_trace_path),
            "status": "ok",
        }


class AttemptExecutionService(CoordinatorSupport):
    """负责单轮尝试的执行与落盘。"""

    def _write_failover_record(self, *, attempt_dir: Path, failure_record: FailureRecord) -> Path | None:
        """在启用窄状态回退时，为下一轮保留一份受控回退建议。"""

        if not self.runtime.enable_narrow_failover or failure_record.failure_type in {"none", ""}:
            return None

        field_changes: dict[str, object] = {
            "build_timeout_sec": {
                "from": self.build_config.build_timeout_sec,
                "to": self.build_config.build_timeout_sec + 300,
            }
        }
        if self.runtime.enable_read_parallel and self.runtime.parallel_read_limit > 1:
            field_changes["parallel_read_limit"] = {
                "from": self.runtime.parallel_read_limit,
                "to": 1,
            }

        current_prompt_profile = self.prompts_config.default_prompt_profile
        alternate_prompt_profile = next(
            (
                profile_name
                for profile_name in self.prompts_config.prompt_profiles
                if profile_name != current_prompt_profile
            ),
            None,
        )
        if alternate_prompt_profile is not None:
            field_changes["prompt_profile"] = {
                "from": current_prompt_profile,
                "to": alternate_prompt_profile,
            }

        failover_record = self.failover_controller.trigger(
            stage_name="failure_analysis",
            trigger_reason=(
                f"单轮尝试失败，失败类型={failure_record.failure_type}，"
                "为下一轮记录受控调用参数回退建议。"
            ),
            from_profile=self.runtime.profile_name or "default",
            to_profile=f"{self.runtime.profile_name or 'default'}:narrow-failover",
            field_changes=field_changes,
        )
        failover_path = attempt_dir / "trace" / "failover.jsonl"
        with failover_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(failover_record.model_dump(mode="json"), ensure_ascii=False) + "\n")
        return failover_path

    def run(self, task_id: str) -> dict[str, Any]:
        """执行最小单轮尝试链路。"""

        task = self.require_task(task_id)
        task_dir = self.workspace_guard.create_task_workspace(task)
        if not (task_dir / "analysis" / "semantic_card.json").exists():
            AnalysisService(self.services).run(task_id)

        attempt_no = self.attempt_repo.next_attempt_no(task_id)
        attempt_dir = self.workspace_guard.create_attempt_workspace(task_dir, attempt_no)

        patch_bundle = self.load_model(task_dir / "input" / "patch_bundle.json", PatchBundle)
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

        ranking_hints = self.dual_memory.build_ranking_hints(
            risk_types=[item.risk_type for item in constraint_report.risk_items]
        )
        planning_hints_path = attempt_dir / "rewrite" / "planning_hints.json"
        planning_hints_path.parent.mkdir(parents=True, exist_ok=True)
        planning_hints_path.write_text(
            json.dumps(ranking_hints, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        try:
            plan = self.planner.plan(
                task_id=task.task_id,
                semantic_card=semantic_card,
                constraint_report=constraint_report,
                ranking_hints=ranking_hints,
            )
        except TypeError:
            # 兼容旧测试桩和早期实现，避免第三期新增排序提示后把前两期基线打断。
            plan = self.planner.plan(
                task_id=task.task_id,
                semantic_card=semantic_card,
                constraint_report=constraint_report,
            )
        rewrite_plan_path = self.json_writer.write_model(plan, attempt_dir / "rewrite" / "rewrite_plan.json")
        rewrite_meta = self.rewriter.execute(
            plan=plan,
            patch_bundle=patch_bundle,
            rewrite_dir=attempt_dir / "rewrite",
            builder=self.builder,
            task_id=task.task_id,
            attempt_no=attempt_no,
        )
        rewritten_patch_path = rewrite_meta["rewritten_patch"]
        apply_precheck_report = rewrite_meta["apply_precheck_report"]
        build_log_path = attempt_dir / "logs" / "build.log"

        build_precheck_path: Path | None = None
        build_summary: BuildSummary | None = None

        if apply_precheck_report.status == "failed":
            build_log = "\n".join(
                [
                    "构建阶段已跳过。",
                    "原因: apply 预检查未通过。",
                    f"目标源码目录: {apply_precheck_report.target_source_dir or 'unknown'}",
                    f"命令: {apply_precheck_report.command or 'unknown'}",
                    f"摘要: {apply_precheck_report.summary}",
                    "",
                    "[stdout]",
                    apply_precheck_report.stdout or "<empty>",
                    "",
                    "[stderr]",
                    apply_precheck_report.stderr or "<empty>",
                ]
            ) + "\n"
            build_log_path.write_text(build_log, encoding="utf-8")
            base_attempt_record = self.builder.start_attempt(task_id=task.task_id, attempt_no=attempt_no)
            attempt_record = base_attempt_record.model_copy(
                update={
                    "candidate_id": plan.candidate_ids[0] if plan.candidate_ids else None,
                    "status": "failed",
                    "failure_type": "patch_apply_failed",
                    "build_log_path": build_log_path,
                    "module_path": None,
                    "rewritten_patch_path": rewritten_patch_path,
                    "finished_at": datetime.now(timezone.utc),
                }
            )
            self.attempt_repo.create_attempt(attempt_record)
            self.attempt_repo.save_evidence_spans(task.task_id, attempt_record.attempt_id, rewrite_evidence.spans)
            failure_record = FailureRecord(
                task_id=task.task_id,
                attempt_id=attempt_record.attempt_id,
                stage_name="rewrite",
                failure_type="patch_apply_failed",
                summary=apply_precheck_report.summary,
                evidence=[
                    item
                    for item in [apply_precheck_report.stdout, apply_precheck_report.stderr]
                    if item
                ][:3],
            )
            build_summary = BuildSummary(
                task_id=task.task_id,
                attempt_id=attempt_record.attempt_id,
                backend=apply_precheck_report.backend,
                builder_cmd=apply_precheck_report.command or self.build_config.kpatch_build_cmd,
                status="precheck_failed",
                summary=apply_precheck_report.summary,
                rewritten_patch_path=rewritten_patch_path,
                source_dir=apply_precheck_report.target_source_dir,
                build_log_path=build_log_path,
                failure_type="patch_apply_failed",
            )
        else:
            attempt_record, build_log, build_precheck, build_summary = self.builder.execute_build(
                task=task,
                attempt_no=attempt_no,
                plan=plan,
                rewritten_patch_path=rewritten_patch_path,
                build_log_path=build_log_path,
            )
            build_precheck_path = self.json_writer.write_model(
                build_precheck,
                attempt_dir / "artifacts" / "build_precheck.json",
            )
            self.attempt_repo.create_attempt(attempt_record)
            self.attempt_repo.save_evidence_spans(task.task_id, attempt_record.attempt_id, rewrite_evidence.spans)
            if attempt_record.status == "failed":
                failure_record = self.failure_classifier.classify_build_log(
                    task_id=task.task_id,
                    attempt_id=attempt_record.attempt_id,
                    build_log=build_log,
                )
            else:
                failure_record = FailureRecord(
                    task_id=task.task_id,
                    attempt_id=attempt_record.attempt_id,
                    stage_name="build",
                    failure_type="none",
                    summary="构建阶段已完成。",
                    evidence=[],
                )
        self.attempt_repo.save_failure_record(failure_record)
        failure_record_path = self.json_writer.write_model(failure_record, attempt_dir / "logs" / "failure_record.json")
        if build_summary is None:
            build_summary = BuildSummary(
                task_id=task.task_id,
                attempt_id=attempt_record.attempt_id,
                backend=apply_precheck_report.backend,
                builder_cmd=apply_precheck_report.command or self.build_config.kpatch_build_cmd,
                status=attempt_record.status,
                summary="构建阶段未返回结构化摘要，已回退为兼容摘要。",
                rewritten_patch_path=rewritten_patch_path,
                build_log_path=attempt_record.build_log_path,
                module_path=attempt_record.module_path,
                failure_type=attempt_record.failure_type,
            )
        build_summary_path = self.json_writer.write_model(
            build_summary,
            attempt_dir / "artifacts" / "build_summary.json",
        )
        failover_record_path = self._write_failover_record(attempt_dir=attempt_dir, failure_record=failure_record)

        history_attempts = self.attempt_repo.list_attempts(task_id)[:-1]
        try:
            validation_report, validation_artifacts = self.validator.run(
                task=task,
                attempt=attempt_record,
                attempt_dir=attempt_dir,
                rewritten_patch_path=rewritten_patch_path,
                build_summary=build_summary,
                constraint_report=constraint_report,
                history_attempts=history_attempts,
            )
        except TypeError:
            validation_report, validation_artifacts = self.validator.run(
                task=task,
                attempt=attempt_record,
                attempt_dir=attempt_dir,
                rewritten_patch_path=rewritten_patch_path,
                build_summary=build_summary,
            )
        validate_log_path = attempt_dir / "logs" / "validate.log"
        validate_log_lines = [
            f"semantic_precheck: {validation_report.semantic_precheck_result.status} - {validation_report.semantic_precheck_result.detail}",
            f"selftest: {validation_report.selftest_result.status} - {validation_report.selftest_result.detail}",
            f"load: {validation_report.load_result.status} - {validation_report.load_result.detail}",
            f"unload: {validation_report.unload_result.status} - {validation_report.unload_result.detail}",
            f"smoke: {validation_report.smoke_result.status} - {validation_report.smoke_result.detail}",
            f"regression: {validation_report.regression_result.status} - {validation_report.regression_result.detail}",
            (
                f"semantic_guard: {validation_report.semantic_guard_result.status}"
                f" - {validation_report.semantic_guard_result.detail}"
            ),
            f"validation_status: {validation_report.status}",
        ]
        if validation_report.notes:
            validate_log_lines.extend(["", "[notes]", *validation_report.notes])
        validate_log_path.write_text("\n".join(validate_log_lines) + "\n", encoding="utf-8")
        self.attempt_repo.save_validation_report(attempt_record.attempt_id, validation_report)

        def resolve_validation_artifact(name: str, fallback: Path, content: str) -> Path:
            """解析验证产物路径，缺失时补一个兼容占位文件。"""

            value = validation_artifacts.get(name)
            resolved = Path(str(value)) if value is not None else fallback
            resolved.parent.mkdir(parents=True, exist_ok=True)
            if not resolved.exists():
                resolved.write_text(content, encoding="utf-8")
            return resolved

        validation_report_path = resolve_validation_artifact(
            "validation_report",
            attempt_dir / "artifacts" / "validation_report.json",
            validation_report.model_dump_json(indent=2),
        )
        semantic_precheck_path = resolve_validation_artifact(
            "semantic_precheck",
            attempt_dir / "artifacts" / "semantic_precheck.json",
            json.dumps({"status": validation_report.semantic_precheck_result.status}, ensure_ascii=False, indent=2),
        )
        semantic_guard_path = resolve_validation_artifact(
            "semantic_guard",
            attempt_dir / "artifacts" / "semantic_guard.json",
            validation_report.semantic_guard_result.model_dump_json(indent=2),
        )
        validation_matrix_path = resolve_validation_artifact(
            "validation_matrix",
            attempt_dir / "artifacts" / "validation_matrix.json",
            validation_report.model_dump_json(indent=2),
        )
        selftest_log_path = resolve_validation_artifact(
            "selftest_log",
            attempt_dir / "logs" / "selftest.log",
            "selftest: fallback placeholder\n",
        )
        load_log_path = resolve_validation_artifact(
            "load_log",
            attempt_dir / "logs" / "load.log",
            "load: fallback placeholder\n",
        )
        unload_log_path = resolve_validation_artifact(
            "unload_log",
            attempt_dir / "logs" / "unload.log",
            "unload: fallback placeholder\n",
        )
        smoke_log_path = resolve_validation_artifact(
            "smoke_log",
            attempt_dir / "logs" / "smoke.log",
            "smoke: fallback placeholder\n",
        )
        regression_log_path = resolve_validation_artifact(
            "regression_log",
            attempt_dir / "logs" / "regression.log",
            "regression: fallback placeholder\n",
        )
        regression_summary_path = resolve_validation_artifact(
            "regression_summary",
            attempt_dir / "artifacts" / "regression_summary.json",
            validation_report.regression_result.model_dump_json(indent=2),
        )
        memory_snapshot = self.dual_memory.record_attempt(
            task=task,
            plan=plan,
            attempt=attempt_record,
            failure_record=failure_record,
            validation_report=validation_report,
        )
        failure_memory_snapshot_path = attempt_dir / "artifacts" / "failure_memory_snapshot.json"
        recipe_memory_snapshot_path = attempt_dir / "artifacts" / "recipe_memory_snapshot.json"
        failure_memory_snapshot_path.write_text(
            json.dumps(memory_snapshot["failure_memory"], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        recipe_memory_snapshot_path.write_text(
            json.dumps(memory_snapshot["recipe_memory"], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

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
            source_paths=[rewrite_plan_path, failure_record_path, semantic_precheck_path, validation_report_path],
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
            mode=self.dispatch_mode_for("rewrite_recipe"),
        )
        trace = self.harness.record_stage(
            trace,
            from_stage="rewrite_recipe",
            to_stage="build",
            reason="改写产物已落盘，完成 apply 预检查后进入构建阶段。",
        )
        trace = self.harness.attach_dispatch_mode(trace, stage_name="build", mode=self.dispatch_mode_for("build"))
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
                mode=self.dispatch_mode_for("failure_analysis"),
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
            mode=self.dispatch_mode_for("validation"),
        )
        trace_artifacts = [
            ("rewrite_plan", rewrite_plan_path, "候选改写规划"),
            ("planning_hints", planning_hints_path, "排序与经验提示"),
            ("rewritten_patch", rewritten_patch_path, "单轮改写结果"),
            ("apply_precheck", rewrite_meta["apply_precheck"], "构建前 apply 预检查"),
            ("build_summary", build_summary_path, "构建阶段结构化摘要"),
            ("failure_record", failure_record_path, "构建失败归因"),
            ("failure_memory_snapshot", failure_memory_snapshot_path, "失败经验快照"),
            ("recipe_memory_snapshot", recipe_memory_snapshot_path, "配方经验快照"),
            ("semantic_precheck", semantic_precheck_path, "验证前语义预检查"),
            ("semantic_guard", semantic_guard_path, "语义守卫结果"),
            ("validation_matrix", validation_matrix_path, "验证矩阵"),
            ("validation_report", validation_report_path, "验证结果摘要"),
        ]
        if failover_record_path is not None:
            trace_artifacts.append(("failover_record", failover_record_path, "窄状态回退建议"))
        for artifact_type, artifact_path, summary in trace_artifacts:
            trace = self.harness.attach_artifact(
                trace,
                artifact_type=artifact_type,
                artifact_path=artifact_path,
                summary=summary,
            )
        trace_path = self.trace_writer.write(trace, attempt_dir / "trace" / "harness_trace.json")
        self.attempt_repo.save_harness_trace(trace, trace_path=trace_path)

        artifact_records: list[tuple[str, Path | None]] = [
            ("rewrite_bootstrap_manifest", rewrite_bootstrap_path),
            ("rewrite_evidence_bundle", rewrite_evidence_path),
            ("rewrite_context_bundle", rewrite_context_path),
            ("rewrite_skill_route", rewrite_packet["route_path"]),
            ("rewrite_prompt_packet", rewrite_packet["prompt_path"]),
            ("rewrite_plan", rewrite_plan_path),
            ("planning_hints", planning_hints_path),
            ("rewritten_patch", rewritten_patch_path),
            ("rewrite_reason", rewrite_meta["rewrite_reason"]),
            ("transformation_trace", rewrite_meta["transformation_trace"]),
            ("apply_precheck", rewrite_meta["apply_precheck"]),
            ("build_log", attempt_record.build_log_path),
            ("build_precheck", build_precheck_path),
            ("build_summary", build_summary_path),
            ("failure_record", failure_record_path),
            ("failure_memory_snapshot", failure_memory_snapshot_path),
            ("recipe_memory_snapshot", recipe_memory_snapshot_path),
            ("validate_log", validate_log_path),
            ("semantic_precheck", semantic_precheck_path),
            ("semantic_guard", semantic_guard_path),
            ("validation_matrix", validation_matrix_path),
            ("selftest_log", selftest_log_path),
            ("load_log", load_log_path),
            ("unload_log", unload_log_path),
            ("smoke_log", smoke_log_path),
            ("regression_log", regression_log_path),
            ("regression_summary", regression_summary_path),
            ("validation_report", validation_report_path),
            ("validation_evidence_bundle", validation_evidence_path),
            ("validation_context_bundle", validation_context_path),
            ("validation_skill_route", validation_packet["route_path"]),
            ("validation_prompt_packet", validation_packet["prompt_path"]),
            ("attempt_state", state_path),
            ("harness_trace", trace_path),
        ]
        if failover_record_path is not None:
            artifact_records.append(("failover_record", failover_record_path))
        for artifact_type, artifact_path in artifact_records:
            if artifact_path is None:
                continue
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
            "failover_record_path": str(failover_record_path) if failover_record_path is not None else None,
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
        evaluation_summary = self.evaluator.summarize(attempts=attempts, artifacts=artifacts)

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
            f"当前成功率为 {evaluation_summary['success_rate']:.0%}，已归档产物类型 {len(evaluation_summary['artifact_type_counts'])} 类。",
        ]
        if attempts:
            latest = attempts[-1]
            explanations.append(f"最近一轮结果为 {latest.status}，失败类型为 {latest.failure_type or '无'}。")

        report = self.report_builder.build_report(
            task=task,
            attempts=attempts,
            artifacts=artifacts,
            evaluation_summary=evaluation_summary,
            explanations=explanations,
        )

        json_path = self.json_writer.write_model(report, task_dir / "reports" / "report.json")
        md_path = self.md_writer.write_report(report, task_dir / "reports" / "report.md")
        evaluation_summary_path = task_dir / "reports" / "evaluation_summary.json"
        evaluation_summary_path.write_text(
            json.dumps(evaluation_summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        for artifact_type, artifact_path in [
            ("reporting_evidence_bundle", report_evidence_path),
            ("reporting_context_bundle", report_context_path),
            ("reporting_bootstrap_manifest", report_bootstrap_path),
            ("reporting_skill_route", report_packet["route_path"]),
            ("reporting_prompt_packet", report_packet["prompt_path"]),
            ("evaluation_summary", evaluation_summary_path),
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
        replay_comparison = self.evaluator.replay_comparison(task_id=task.task_id, attempts=attempts, task_dir=task_dir)
        return self.replay_harness.build_summary(
            task=task,
            task_dir=task_dir,
            attempts=attempts,
            latest_trace=latest_trace,
            replay_comparison=replay_comparison,
        )
