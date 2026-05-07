"""任务编排相关 service"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from patchweaver.analyzer.repair_intent_service import RepairIntentBuilder
from patchweaver.builder.source_preparer import prepare_stable_source_baseline
from patchweaver.context.bootstrap_registry import BootstrapRegistry
from patchweaver.harness.attempt_engine import AttemptEngine
from patchweaver.harness.dispatch_policy import dispatch_mode, is_write_stage
from patchweaver.models.attempt import BuildSummary, FailureRecord
from patchweaver.models.constraint import ConstraintReport
from patchweaver.models.context import BootstrapManifest, ContextBundle
from patchweaver.models.evidence import EvidenceBundle, EvidenceSpan
from patchweaver.models.patch import PatchBundle
from patchweaver.models.rewrite import RewritePlan
from patchweaver.models.semantic import RepairIntent, SemanticCard
from patchweaver.models.task import TaskContext
from patchweaver.rewriter.effectiveness import build_route_effectiveness_report, write_route_effectiveness_report
from patchweaver.runtime_inspector import render_machine_profile_summary, validate_task_binding
from patchweaver.utils.path_policy import relativize_payload, to_project_relative

ModelT = TypeVar("ModelT", bound=BaseModel)


@dataclass(slots=True)
class TaskRunnerServices:
    """收拢主流程运行时依赖"""

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
    rag_context_injector: Any | None = None


class CoordinatorSupport:
    """为各阶段 service 提供共享依赖和辅助方法"""

    def __init__(self, services: TaskRunnerServices) -> None:
        """把共享依赖绑定到实例上，方便阶段 service 直接使用"""

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
        self.rag_context_injector = services.rag_context_injector
        self.repair_intent_builder = RepairIntentBuilder()

    def build_bootstrap_manifest(self) -> BootstrapManifest:
        """按当前配置整理 bootstrap 片段"""

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
        """为单个阶段输出 route 和 prompt 产物"""

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
        """按当前运行时开关返回阶段调度模式"""

        return dispatch_mode(stage_name, enable_read_parallel=self.runtime.enable_read_parallel)

    def require_task(self, task_id: str) -> TaskContext:
        """读取任务，不存在时直接报错"""

        task = self.task_repo.get_task(task_id)
        if task is None:
            raise ValueError(f"未找到任务：{task_id}")
        return task

    def load_model(self, path: Path, model_type: type[ModelT]) -> ModelT:
        """按模型类型读取本地 JSON 文件"""

        return model_type.model_validate_json(path.read_text(encoding="utf-8"))

    def build_evidence_bundle(self, *, source_paths: list[Path | None], bundle_tag: str) -> EvidenceBundle:
        """根据已有产物生成一份最小证据包"""

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
                    source_path=to_project_relative(self.runtime.project_root, source_path) or "",
                    excerpt=excerpt,
                    start_line=1,
                    end_line=20,
                    score=1.0,
                )
            )
        return EvidenceBundle(evidence_ids=evidence_ids, spans=spans, memory_hits=[])

    def assemble_context(
        self,
        *,
        stage_name: str,
        evidence_bundle: EvidenceBundle,
        task: TaskContext | None = None,
        patch_bundle: PatchBundle | None = None,
        semantic_card: SemanticCard | None = None,
        constraint_report: ConstraintReport | None = None,
        rewrite_plan: RewritePlan | None = None,
        failure_record: FailureRecord | None = None,
    ) -> ContextBundle:
        """按阶段预算生成上下文包，并在可用时注入 RAG 证据。"""

        prompt_profile = self.prompts_config.prompt_profiles.get(self.prompts_config.default_prompt_profile)
        max_evidence = prompt_profile.max_evidence_snippets if prompt_profile is not None else 8
        max_memory_hits = prompt_profile.max_memory_hits if prompt_profile is not None else 3
        rag_result = (
            self.rag_context_injector.inject(
                stage_name=stage_name,
                task=task,
                evidence_bundle=evidence_bundle,
                patch_bundle=patch_bundle,
                semantic_card=semantic_card,
                constraint_report=constraint_report,
                rewrite_plan=rewrite_plan,
                failure_record=failure_record,
            )
            if self.rag_context_injector is not None
            else None
        )
        stage_evidence_bundle = rag_result.evidence_bundle if rag_result is not None else evidence_bundle
        memory_hits = self.dual_memory.recall(
            stage_name=stage_name,
            evidence_bundle=stage_evidence_bundle,
            limit=max_memory_hits,
        )
        enriched_bundle = stage_evidence_bundle.model_copy(update={"memory_hits": memory_hits})
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
        if rag_result is not None:
            if rag_result.error:
                notes.append(f"RAG 注入跳过: {rag_result.error}")
            elif rag_result.added_count:
                selected_rag_hits = sum(1 for span in context_bundle.source_spans if span.source_type == "rag")
                notes.append(f"RAG 命中注入: {rag_result.added_count}，进入上下文: {selected_rag_hits}")
                if rag_result.subsystem:
                    notes.append(f"RAG 子系统过滤: {rag_result.subsystem}")
        if context_bundle.token_cost > budget["token_limit"]:
            notes.append("当前上下文已超过阶段预算，后续应补充裁剪策略。")
        return context_bundle.model_copy(update={"notes": notes})


class AnalysisService(CoordinatorSupport):
    """负责分析阶段的任务编排"""

    def run(self, task_id: str) -> dict[str, Any]:
        """执行最小分析链路"""

        task = self.require_task(task_id)
        task_dir = self.workspace_guard.create_task_workspace(task)
        self.workspace_guard.ensure_analysis_workspace(task_dir)

        # 先把最原始的 patch 输入固定下来
        # 后面改写、构建、报告都复用这组分析输入
        raw_patch_path = task_dir / "input" / "raw_patch.patch"
        bundle = self.retriever.fetch_patch_bundle(task=task, raw_patch_path=raw_patch_path)
        source_fetch_trace_path = getattr(self.retriever, "last_fetch_trace_path", None)
        normalized_patch_path = task_dir / "normalized" / "normalized.patch"
        self.patch_normalizer.normalize(raw_patch_path, normalized_patch_path)
        bundle.normalized_patch_path = normalized_patch_path
        if not bundle.affected_files:
            bundle.affected_files = self.patch_normalizer.extract_affected_files(
                normalized_patch_path.read_text(encoding="utf-8")
            )

        semantic_card = self.semantic_analyzer.analyze(task, bundle)
        bootstrap_manifest = self.build_bootstrap_manifest()

        # 先把 patch bundle、来源证据和确定性语义草稿固定下来
        # 模型补全和约束诊断都会复用这批输入
        patch_bundle_path = self.json_writer.write_model(bundle, task_dir / "input" / "patch_bundle.json")
        source_evidence_path = task_dir / "input" / "source_evidence.json"
        source_evidence_path.write_text(
            json.dumps([item.model_dump() for item in bundle.source_evidence], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        semantic_card_path = self.json_writer.write_model(semantic_card, task_dir / "analysis" / "semantic_card.json")
        bootstrap_manifest_path = self.json_writer.write_model(
            bootstrap_manifest,
            task_dir / "analysis" / "bootstrap" / "bootstrap_manifest.json",
        )

        retrieval_stage_sources = [patch_bundle_path, source_evidence_path, normalized_patch_path, raw_patch_path]
        retrieval_evidence_bundle = self.build_evidence_bundle(
            source_paths=retrieval_stage_sources,
            bundle_tag="ANL-RTV",
        )
        retrieval_context_bundle = self.assemble_context(
            stage_name="retrieval",
            evidence_bundle=retrieval_evidence_bundle,
            task=task,
            patch_bundle=bundle,
        )

        # semantic_card 阶段的补全不能依赖旧的 constraint_report
        # 语义阶段上下文只吃真实输入，语义草稿单独通过 draft_card 传给模型补全器
        semantic_stage_sources = [patch_bundle_path, source_evidence_path, normalized_patch_path, raw_patch_path]
        semantic_evidence_bundle = self.build_evidence_bundle(
            source_paths=semantic_stage_sources,
            bundle_tag="ANL-SEM",
        )
        semantic_context_bundle = self.assemble_context(
            stage_name="semantic_card",
            evidence_bundle=semantic_evidence_bundle,
            task=task,
            patch_bundle=bundle,
            semantic_card=semantic_card,
        )

        # 这三个 stage packet 会被回放、调试页和报告复用
        # 顺序固定成 retrieval -> semantic_card -> constraint_diagnosis
        retrieval_packet = self.materialize_stage_packet(
            stage_name="retrieval",
            schema_name="PatchBundle",
            context_bundle=retrieval_context_bundle,
            bootstrap_manifest=bootstrap_manifest,
            base_dir=task_dir / "analysis",
        )
        semantic_packet = self.materialize_stage_packet(
            stage_name="semantic_card",
            schema_name="SemanticCard",
            context_bundle=semantic_context_bundle,
            bootstrap_manifest=bootstrap_manifest,
            base_dir=task_dir / "analysis",
        )
        semantic_card, semantic_enrichment_trace = self.semantic_analyzer.maybe_enrich(
            task=task,
            patch_bundle=bundle,
            draft_card=semantic_card,
            prompt_packet=semantic_packet["prompt_packet"],
            context_bundle=semantic_context_bundle,
            route=semantic_packet["route"],
            prompt_packet_path=semantic_packet["prompt_path"],
            source_evidence_path=source_evidence_path,
        )
        semantic_card_path = self.json_writer.write_model(
            semantic_card,
            task_dir / "analysis" / "semantic_card.json",
        )
        semantic_enrichment_path = self.json_writer.write_model(
            semantic_enrichment_trace,
            task_dir / "analysis" / "trace" / "semantic_card_enrichment.json",
        )
        repair_intent = self.repair_intent_builder.build(
            patch_bundle=bundle,
            semantic_card=semantic_card,
            patch_text=normalized_patch_path.read_text(encoding="utf-8", errors="replace")
            if normalized_patch_path.exists()
            else raw_patch_path.read_text(encoding="utf-8", errors="replace"),
        )
        repair_intent_path = self.json_writer.write_model(
            repair_intent,
            task_dir / "analysis" / "repair_intent.json",
        )

        # 语义补全一旦产生增量，约束诊断必须在同一轮重新计算
        # 下游使用的 constraint report、context bundle 和 prompt packet 都以最终语义卡片为准
        semantic_card_source = "enriched" if semantic_enrichment_trace.applied else "deterministic"
        constraint_report = self.constraint_diagnoser.diagnose(
            bundle,
            semantic_card=semantic_card,
            semantic_card_source=semantic_card_source,
            semantic_card_enriched=semantic_enrichment_trace.applied,
        )
        constraint_report_path = self.json_writer.write_model(
            constraint_report,
            task_dir / "analysis" / "constraint_report.json",
        )
        analysis_sources = [patch_bundle_path, source_evidence_path, normalized_patch_path, semantic_card_path, repair_intent_path]
        evidence_bundle = self.build_evidence_bundle(source_paths=analysis_sources, bundle_tag="ANL")
        context_bundle = self.assemble_context(
            stage_name="constraint_diagnosis",
            evidence_bundle=evidence_bundle,
            task=task,
            patch_bundle=bundle,
            semantic_card=semantic_card,
            constraint_report=constraint_report,
        )
        evidence_bundle_path = self.json_writer.write_model(
            evidence_bundle,
            task_dir / "analysis" / "context" / "evidence_bundle.json",
        )
        context_bundle_path = self.json_writer.write_model(
            context_bundle,
            task_dir / "analysis" / "context" / "context_bundle.json",
        )
        constraint_packet = self.materialize_stage_packet(
            stage_name="constraint_diagnosis",
            schema_name="ConstraintReport",
            context_bundle=context_bundle,
            bootstrap_manifest=bootstrap_manifest,
            base_dir=task_dir / "analysis",
        )

        # 分析阶段单独记一份 trace
        # 这里不用真正的 attempt 编号，避免和改写尝试混在一起
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
        if source_fetch_trace_path is not None and source_fetch_trace_path.exists():
            analysis_trace = self.harness.attach_artifact(
                analysis_trace,
                artifact_type="source_fetch_trace",
                artifact_path=source_fetch_trace_path,
                summary="来源抓取轨迹",
            )
        analysis_trace = self.harness.attach_artifact(
            analysis_trace,
            artifact_type="semantic_card",
            artifact_path=semantic_card_path,
            summary="语义分析结果",
        )
        analysis_trace = self.harness.attach_artifact(
            analysis_trace,
            artifact_type="semantic_card_enrichment",
            artifact_path=semantic_enrichment_path,
            summary="语义卡片模型补全过程留痕",
        )
        analysis_trace = self.harness.attach_artifact(
            analysis_trace,
            artifact_type="repair_intent",
            artifact_path=repair_intent_path,
            summary="可驱动改写执行的修复意图",
        )
        analysis_trace = self.harness.attach_artifact(
            analysis_trace,
            artifact_type="constraint_report",
            artifact_path=constraint_report_path,
            summary="约束诊断结果",
        )
        analysis_trace_path = self.trace_writer.write(analysis_trace, task_dir / "analysis" / "trace" / "analysis_trace.json")

        # 一层存业务对象，一层存 artifact 索引
        # 后面状态页和报告页会同时用到这两组数据
        self.task_repo.save_patch_bundle(bundle)
        self.task_repo.update_task_status(task.task_id, status="analyzed", current_attempt=0)

        for artifact_type, artifact_path in [
            ("raw_patch", raw_patch_path),
            ("normalized_patch", normalized_patch_path),
            ("patch_bundle", patch_bundle_path),
            ("source_evidence", source_evidence_path),
            ("source_fetch_trace", source_fetch_trace_path),
            ("semantic_card", semantic_card_path),
            ("semantic_card_enrichment", semantic_enrichment_path),
            ("repair_intent", repair_intent_path),
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
            if artifact_path is None:
                continue
            self.artifact_repo.add_artifact(task_id=task.task_id, artifact_type=artifact_type, artifact_path=artifact_path)

        payload = {
            "command": "analyze",
            "task_id": task.task_id,
            "patch_bundle_path": to_project_relative(self.runtime.project_root, patch_bundle_path),
            "source_evidence_path": to_project_relative(self.runtime.project_root, source_evidence_path),
            "semantic_card_path": to_project_relative(self.runtime.project_root, semantic_card_path),
            "semantic_card_enrichment_path": to_project_relative(self.runtime.project_root, semantic_enrichment_path),
            "repair_intent_path": to_project_relative(self.runtime.project_root, repair_intent_path),
            "constraint_report_path": to_project_relative(self.runtime.project_root, constraint_report_path),
            "bootstrap_manifest_path": to_project_relative(self.runtime.project_root, bootstrap_manifest_path),
            "analysis_trace_path": to_project_relative(self.runtime.project_root, analysis_trace_path),
            "status": "ok",
        }
        if source_fetch_trace_path is not None and source_fetch_trace_path.exists():
            payload["source_fetch_trace_path"] = to_project_relative(self.runtime.project_root, source_fetch_trace_path)
        return payload


class AttemptExecutionService(CoordinatorSupport):
    """负责单轮尝试的执行与落盘"""

    def _normalize_target_state_outcome(
        self,
        *,
        attempt_record: Any,
        build_summary: BuildSummary | None,
        build_log: str,
        build_log_path: Path,
    ) -> tuple[Any, BuildSummary | None, str]:
        """把 target_state 场景在 run/build/replay 三条口径上统一收口。"""

        target_state = attempt_record.target_state or (build_summary.target_state if build_summary is not None else None)
        saw_already_patched_fallback = (
            build_summary is not None
            and build_summary.build_exec_status == "not_run"
            and "当前源码树已命中 target_already_patched" in build_log
        )
        if target_state is None and saw_already_patched_fallback:
            target_state = "target_already_patched"
        if target_state is None:
            return attempt_record, build_summary, build_log

        summary_text = (
            build_summary.summary
            if build_summary is not None and build_summary.summary
            else f"本轮按 {target_state} 收口。"
        )
        if (
            target_state == "target_already_patched"
            and saw_already_patched_fallback
            and "备用源码树未能提供可继续构建的落点" not in summary_text
        ):
            summary_text = "首选源码树已包含该补丁，备用源码树未能提供可继续构建的落点，本轮按目标态已修复收口"

        if target_state == "target_already_patched" and saw_already_patched_fallback and "[build normalization]" not in build_log:
            build_log = build_log.rstrip("\n") + "\n\n[build normalization]\n首选源码树命中 target_already_patched\n备用源码树未能通过 apply 预检查\n阶段最终结果统一收口为 target_already_patched\n"
            build_log_path.write_text(build_log, encoding="utf-8")

        attempt_record = attempt_record.model_copy(
            update={
                "status": "target_state",
                "failure_type": target_state,
                "build_exec_status": "not_run",
                "target_state": target_state,
            }
        )
        if build_summary is not None:
            build_summary = build_summary.model_copy(
                update={
                    "status": "not_run",
                    "summary": summary_text,
                    "failure_type": target_state,
                    "build_exec_status": "not_run",
                    "target_state": target_state,
                }
            )
        return attempt_record, build_summary, build_log

    def _build_target_state_failure_record(
        self,
        *,
        task_id: str,
        attempt_id: str,
        build_summary: BuildSummary | None,
        build_log: str,
        target_state: str,
    ) -> FailureRecord:
        """为 target_state 结果生成一条可复用的失败归因记录"""

        evidence: list[str] = []
        for line in build_log.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if (
                "target_already_patched" in stripped
                or "目标源码已包含该补丁" in stripped
                or "备用源码树" in stripped
            ) and stripped not in evidence:
                evidence.append(stripped)
            if len(evidence) >= 3:
                break

        summary = (
            build_summary.summary
            if build_summary is not None and build_summary.summary
            else "目标源码已包含该补丁，本轮按目标态已修复收口"
        )
        return FailureRecord(
            task_id=task_id,
            attempt_id=attempt_id,
            stage_name="build",
            failure_type=target_state,
            summary=summary,
            evidence=evidence,
        )

    def _write_failover_record(self, *, attempt_dir: Path, failure_record: FailureRecord) -> Path | None:
        """在启用窄状态回退时，为下一轮保留一份受控回退建议"""

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

    def _previous_attempt_dir(self, *, task_dir: Path, attempt_no: int) -> Path | None:
        """返回上一轮 attempt 目录"""

        if attempt_no <= 1:
            return None
        previous = task_dir / "attempts" / f"{attempt_no - 1:03d}"
        return previous if previous.exists() else None

    def _attach_attempt_diagnostics(
        self,
        *,
        failure_record: FailureRecord,
        route_effectiveness: dict[str, Any],
        section_change_report_path: Path | None,
        build_log: str,
    ) -> FailureRecord:
        """把路线有效性和专项改写结果补进失败归因"""

        details = dict(failure_record.diagnostic_details or {})
        if failure_record.failure_type == "patch_apply_failed" and "patch_apply" not in details:
            details["patch_apply"] = self.failure_classifier.diagnose_patch_apply_failure(build_log=build_log)
        details["route_effectiveness"] = route_effectiveness
        if section_change_report_path is not None and section_change_report_path.exists():
            try:
                details["section_change_avoidance"] = json.loads(section_change_report_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                details["section_change_avoidance"] = {"status": "unreadable"}

        evidence = list(failure_record.evidence)
        if route_effectiveness.get("status") == "ineffective_retry":
            evidence.append("路线有效性检查: ineffective_retry，本轮补丁形态与上一轮基本一致")
        details["agent_next_action"] = self._derive_agent_next_action(
            failure_record=failure_record,
            diagnostic_details=details,
        )
        return failure_record.model_copy(update={"diagnostic_details": details, "evidence": evidence[:6]})

    def _should_retry_apply_failure_in_builder(self, apply_precheck_report: Any) -> bool:
        """判断 apply 预检查失败后是否交给 builder 做源码对齐"""

        if getattr(apply_precheck_report, "status", None) != "failed":
            return False
        failure_type = (
            getattr(apply_precheck_report, "target_state", None)
            or getattr(apply_precheck_report, "failure_type", None)
            or ""
        )
        if failure_type == "target_already_patched":
            return bool(getattr(self.build_config, "auto_switch_source_tree", False))
        if failure_type != "patch_apply_failed":
            return False
        return bool(
            getattr(self.build_config, "auto_switch_source_tree", False)
            or getattr(self.build_config, "auto_reverse_source_tree", False)
        )

    def _ensure_failure_specific_diagnostics(
        self,
        *,
        failure_record: FailureRecord,
        build_log: str,
    ) -> FailureRecord:
        """保证失败大类落盘前带上对应子诊断"""

        details = dict(failure_record.diagnostic_details or {})
        if failure_record.failure_type == "patch_apply_failed" and "patch_apply" not in details:
            details["patch_apply"] = self.failure_classifier.diagnose_patch_apply_failure(build_log=build_log)
        details["agent_next_action"] = self._derive_agent_next_action(
            failure_record=failure_record,
            diagnostic_details=details,
        )
        if details == (failure_record.diagnostic_details or {}):
            return failure_record
        return failure_record.model_copy(update={"diagnostic_details": details})

    def _derive_agent_next_action(
        self,
        *,
        failure_record: FailureRecord,
        diagnostic_details: dict[str, Any],
    ) -> dict[str, Any]:
        """把失败归因转换成下一轮可执行动作"""

        failure_type = failure_record.failure_type
        if failure_type == "patch_apply_failed":
            patch_apply = diagnostic_details.get("patch_apply") or {}
            if isinstance(patch_apply, dict) and patch_apply.get("stable_source_alignment_required"):
                return {
                    "action": "prepare_unpatched_stable_source_baseline",
                    "reason": "patch 上下文与当前源码树不一致，需要切换到修复提交父版本或等价未修复源码树",
                    "retry_scope": "source_baseline",
                    "retryable_after_environment_update": True,
                }
            return {
                "action": "inspect_patch_apply_failure",
                "reason": "apply 失败证据不足，先查看 conflict_files 和 precheck stderr",
                "retry_scope": "diagnostics",
            }
        if failure_type in {
            "kpatch_constraint",
            "kpatch_constraint_unresolved",
            "kpatch_symbol_bundle_constraint",
            "kpatch_section_symbol_offset_constraint",
        }:
            kpatch_details = diagnostic_details.get("kpatch_constraint") or {}
            if isinstance(kpatch_details, dict) and kpatch_details.get("constraint_kind") == "symbol_bundle_offset":
                return {
                    "action": "check_vendor_baseline_then_section_symbol_rewrite",
                    "reason": "kpatch 后端在符号打包阶段发现 section 符号偏移，需先确认 vendor baseline 与目标内核完全匹配，再考虑函数入口 guard 或 section 收缩",
                    "retry_scope": "source_baseline_then_rewrite_strategy",
                    "retryable_after_environment_update": True,
                }
            rewrite_classification = (
                kpatch_details.get("rewrite_classification") if isinstance(kpatch_details, dict) else {}
            )
            if isinstance(rewrite_classification, dict):
                next_strategy = rewrite_classification.get("next_strategy")
                if next_strategy == "semantic_guard_rewrite":
                    return {
                        "action": "semantic_guard_rewrite",
                        "reason": "当前 kpatch 约束样例适合先尝试函数局部 guard 等价改写",
                        "retry_scope": "rewrite_strategy",
                    }
                if next_strategy == "callback_or_shadow_state_strategy":
                    return {
                        "action": "callback_or_shadow_state_strategy",
                        "reason": "补丁涉及数据状态或类型定义，需要 callback/shadow 路线而不是继续函数局部收缩",
                        "retry_scope": "rewrite_strategy",
                    }
            section_report = diagnostic_details.get("section_change_avoidance") or {}
            dependency_gap = isinstance(section_report, dict) and bool(section_report.get("dependency_gap"))
            return {
                "action": "section_change_avoidance" if not dependency_gap else "resolve_dependency_gap_or_mark_unfixable",
                "reason": "kpatch 后端约束需要收缩改写半径并保持依赖" if not dependency_gap else "收缩改写存在依赖缺口，继续硬重试价值较低",
                "retry_scope": "rewrite_strategy",
            }
        if failure_type == "compile_failed":
            return {
                "action": "adjust_build_target_or_dependencies",
                "reason": "真实编译失败应优先检查模块目标、依赖模块和构建日志根因",
                "retry_scope": "build_target",
            }
        if failure_type == "feature_not_enabled":
            return {
                "action": "exclude_from_positive_pool_or_enable_kernel_feature",
                "reason": "当前验证内核未编译该子系统，不能计入正向 .ko 成功率",
                "retry_scope": "environment_profile",
            }
        if failure_type == "build_cache_incomplete":
            return {
                "action": "prepare_stable_build_cache",
                "reason": "当前源码基线已可应用补丁，但缺少 Module.symvers、vmlinux.o 或 vmlinux，需先预热源码树再进入 kpatch-build",
                "retry_scope": "build_cache",
                "retryable_after_environment_update": True,
            }
        return {
            "action": "stop_or_manual_review",
            "reason": f"{failure_type or 'unknown'} 暂无自动重试策略",
            "retry_scope": "manual",
        }

    def _maybe_mark_unresolved_kpatch_constraint(
        self,
        *,
        task: TaskContext,
        task_dir: Path,
        attempt_record: Any,
        build_summary: BuildSummary | None,
        failure_record: FailureRecord,
        route_effectiveness: dict[str, Any] | None = None,
    ) -> tuple[Any, BuildSummary | None, FailureRecord]:
        """连续多轮命中同一 section 约束时收口为未解决后端约束"""

        if failure_record.failure_type != "kpatch_constraint":
            return attempt_record, build_summary, failure_record
        if attempt_record.attempt_no < max(1, int(task.max_attempts or 1)):
            return attempt_record, build_summary, failure_record
        route_effectiveness = route_effectiveness or {}
        if route_effectiveness.get("status") == "ineffective_retry":
            details = dict(failure_record.diagnostic_details)
            details["unresolved_decision"] = {
                "status": "deferred_by_ineffective_retry",
                "reason": "本轮只是切换 recipe 名称，rewritten.patch 形态未实际变化，不计入已尝试不同改写路线",
                "route_effectiveness": route_effectiveness,
            }
            failure_record = failure_record.model_copy(update={"diagnostic_details": details})
            return attempt_record, build_summary, failure_record

        history = self._load_failure_record_payloads(task_dir=task_dir, current=failure_record)
        signatures = [self._section_constraint_signature(item) for item in history]
        signatures = [item for item in signatures if item]
        recipes = self._load_attempt_recipes(task_dir=task_dir, max_attempt_no=attempt_record.attempt_no)
        if len(signatures) < 2 or len(set(signatures)) != 1 or len(set(recipes)) < 2:
            return attempt_record, build_summary, failure_record

        unresolved_summary = (
            f"已连续 {len(signatures)} 轮不同改写路线命中同一 kpatch section 约束，"
            "当前收口为 kpatch_constraint_unresolved"
        )
        details = dict(failure_record.diagnostic_details)
        details["unresolved_decision"] = {
            "status": "kpatch_constraint_unresolved",
            "reason": "已连续多轮不同改写路线命中同一 kpatch section 约束",
            "attempts_observed": len(signatures),
            "section_signature": signatures[0],
            "recipes_observed": recipes,
        }
        evidence = list(failure_record.evidence)
        evidence.append(unresolved_summary)
        failure_record = failure_record.model_copy(
            update={
                "failure_type": "kpatch_constraint_unresolved",
                "summary": unresolved_summary,
                "evidence": evidence[:6],
                "diagnostic_details": details,
            }
        )
        attempt_record = attempt_record.model_copy(update={"failure_type": "kpatch_constraint_unresolved"})
        if build_summary is not None:
            build_summary = build_summary.model_copy(
                update={
                    "failure_type": "kpatch_constraint_unresolved",
                    "summary": unresolved_summary,
                }
            )
        return attempt_record, build_summary, failure_record

    def _load_failure_record_payloads(self, *, task_dir: Path, current: FailureRecord) -> list[dict[str, Any]]:
        """读取历史 failure_record，加上当前轮归因"""

        payloads: list[dict[str, Any]] = []
        for path in sorted((task_dir / "attempts").glob("[0-9][0-9][0-9]/logs/failure_record.json")):
            try:
                payloads.append(json.loads(path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
        payloads.append(current.model_dump(mode="json"))
        return payloads

    def _section_constraint_signature(self, payload: dict[str, Any]) -> str | None:
        """抽取 section 约束签名"""

        failure_type = str(payload.get("failure_type") or "")
        if failure_type not in {"kpatch_constraint", "kpatch_constraint_unresolved"}:
            return None
        details = payload.get("diagnostic_details") or {}
        if not isinstance(details, dict):
            return None
        constraint = details.get("kpatch_constraint") or {}
        if not isinstance(constraint, dict):
            return None
        changes = constraint.get("section_changes") or []
        if not changes or not isinstance(changes[0], dict):
            return str(constraint.get("constraint_kind") or "kpatch_constraint")
        first = changes[0]
        return f"{constraint.get('constraint_kind') or 'unsupported_section_change'}:{first.get('object_file')}"

    def _load_attempt_recipes(self, *, task_dir: Path, max_attempt_no: int) -> list[str]:
        """读取截至当前轮的 recipe 序列"""

        recipes: list[str] = []
        for attempt_no in range(1, max_attempt_no + 1):
            path = task_dir / "attempts" / f"{attempt_no:03d}" / "rewrite" / "rewrite_plan.json"
            if not path.exists():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            recipe = str(payload.get("selected_recipe") or "")
            if recipe:
                recipes.append(recipe)
        return recipes

    def _load_task_patch_text(self, *, task_dir: Path, patch_bundle: PatchBundle) -> str:
        """读取任务输入 patch 文本"""

        candidates = [
            patch_bundle.normalized_patch_path,
            patch_bundle.raw_patch_path,
            task_dir / "input" / "normalized.patch",
            task_dir / "input" / "raw_patch.patch",
        ]
        for candidate in candidates:
            if candidate is None:
                continue
            path = Path(candidate)
            if path.exists():
                return path.read_text(encoding="utf-8", errors="replace")
        return ""

    def _ensure_stable_baseline_preflight(self, *, task_dir: Path, patch_bundle: PatchBundle) -> Path | None:
        """在 full run 前尝试准备 stable 未修复源码基线"""

        preflight_path = task_dir / "input" / "stable_baseline_preflight.json"
        baseline_ref = str(patch_bundle.stable_source_baseline_ref or "").strip()
        payload: dict[str, object] = {
            "status": "skipped",
            "reason": "patch_bundle 未提供 stable_source_baseline_ref",
            "baseline_ref": baseline_ref or None,
            "stable_source_git_dir": self.build_config.stable_source_git_dir,
            "stable_kernel_src_dir": self.build_config.stable_kernel_src_dir,
        }
        if not baseline_ref:
            preflight_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return preflight_path

        stable_kernel_src_dir = Path(str(self.build_config.stable_kernel_src_dir or ""))
        if self._looks_like_kernel_source(stable_kernel_src_dir):
            payload.update(
                {
                    "status": "reused",
                    "reason": "已配置可用 stable_kernel_src_dir",
                    "stable_kernel_src_dir": str(stable_kernel_src_dir),
                }
            )
            preflight_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return preflight_path

        stable_git_dir = Path(str(self.build_config.stable_source_git_dir or ""))
        if not self.build_config.stable_source_git_dir or not stable_git_dir.exists():
            payload.update(
                {
                    "status": "blocked",
                    "reason": "未配置可用 stable_source_git_dir，无法自动准备未修复 stable source baseline",
                    "agent_next_action": "configure_stable_source_git_dir",
                }
            )
            preflight_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return preflight_path

        try:
            result = prepare_stable_source_baseline(
                stable_git_dir=stable_git_dir,
                baseline_ref=baseline_ref,
                output_root=Path(self.build_config.stable_source_cache_dir),
                config_source=Path(self.build_config.kernel_src_dir) / ".config",
                build_config_path=self.runtime.config_dir / "build.yaml",
                write_build_config=True,
            )
        except Exception as exc:
            payload.update(
                {
                    "status": "failed",
                    "reason": f"stable baseline 准备失败: {exc}",
                    "agent_next_action": "inspect_stable_source_baseline_failure",
                }
            )
            preflight_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return preflight_path

        self.build_config.stable_kernel_src_dir = result.output_dir
        if hasattr(self.builder, "build_config"):
            self.builder.build_config.stable_kernel_src_dir = result.output_dir
        payload.update(
            {
                "status": "prepared",
                "reason": "已按 stable_source_baseline_ref 准备未修复源码基线",
                **result.to_payload(),
            }
        )
        preflight_path.write_text(json.dumps(relativize_payload(payload, self.runtime.project_root), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return preflight_path

    def _looks_like_kernel_source(self, path: Path) -> bool:
        """判断目录是否像可用内核源码树"""

        return bool(str(path)) and path.exists() and (path / "Makefile").exists()

    def run(self, task_id: str) -> dict[str, Any]:
        """执行最小单轮尝试链路"""

        task = self.require_task(task_id)
        task_dir = self.workspace_guard.create_task_workspace(task)
        # run 是主链入口，分析产物没准备好时先补分析阶段
        if not (task_dir / "analysis" / "semantic_card.json").exists():
            AnalysisService(self.services).run(task_id)

        patch_bundle = self.load_model(task_dir / "input" / "patch_bundle.json", PatchBundle)
        semantic_card = self.load_model(task_dir / "analysis" / "semantic_card.json", SemanticCard)
        repair_intent_path = task_dir / "analysis" / "repair_intent.json"
        repair_intent = (
            self.load_model(repair_intent_path, RepairIntent)
            if repair_intent_path.exists()
            else self.repair_intent_builder.build(
                patch_bundle=patch_bundle,
                semantic_card=semantic_card,
                patch_text=self._load_task_patch_text(task_dir=task_dir, patch_bundle=patch_bundle),
            )
        )
        if not repair_intent_path.exists():
            self.json_writer.write_model(repair_intent, repair_intent_path)
        stable_baseline_preflight_path = self._ensure_stable_baseline_preflight(
            task_dir=task_dir,
            patch_bundle=patch_bundle,
        )

        binding_ok, binding_message, current_machine_profile = validate_task_binding(task, self.build_config)
        if not binding_ok:
            raise RuntimeError(binding_message)

        constraint_report = self.load_model(task_dir / "analysis" / "constraint_report.json", ConstraintReport)
        bootstrap_manifest = self.build_bootstrap_manifest()
        attempt_no = self.attempt_repo.next_attempt_no(task_id)
        # 先种一条 running 状态
        # 后面任何失败都能明确回到这轮 attempt
        seed_attempt_record = self.builder.start_attempt(task_id=task.task_id, attempt_no=attempt_no).model_copy(
            update={"status": "running"}
        )
        self.attempt_repo.save_attempt(seed_attempt_record)
        self.task_repo.update_task_status(task.task_id, status="running", current_attempt=attempt_no)
        attempt_dir = self.workspace_guard.create_attempt_workspace(task_dir, attempt_no)
        environment_check_path = attempt_dir / "logs" / "environment_check.log"
        environment_check_path.write_text(
            "\n".join([binding_message, render_machine_profile_summary(current_machine_profile)]) + "\n",
            encoding="utf-8",
        )

        # 改写阶段只吃已经确认过的分析产物
        # 这样上下文来源稳定，也方便解释本轮为什么这么改
        rewrite_evidence = self.build_evidence_bundle(
            source_paths=[
                task_dir / "input" / "patch_bundle.json",
                task_dir / "analysis" / "semantic_card.json",
                task_dir / "analysis" / "repair_intent.json",
                task_dir / "analysis" / "constraint_report.json",
            ],
            bundle_tag=f"RW{attempt_no:03d}",
        )
        rewrite_context = self.assemble_context(
            stage_name="rewrite_recipe",
            evidence_bundle=rewrite_evidence,
            task=task,
            patch_bundle=patch_bundle,
            semantic_card=semantic_card,
            constraint_report=constraint_report,
        )
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
            task_id=task.task_id,
            risk_types=[item.risk_type for item in constraint_report.risk_items]
        )
        planning_hints_path = attempt_dir / "rewrite" / "planning_hints.json"
        planning_hints_path.parent.mkdir(parents=True, exist_ok=True)
        planning_hints_path.write_text(
            json.dumps(ranking_hints, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        try:
            # 第三期后 planner 增加了 ranking_hints 输入
            # 这里保留兼容分支，避免老测试桩直接断掉
            plan = self.planner.plan(
                task_id=task.task_id,
                semantic_card=semantic_card,
                constraint_report=constraint_report,
                repair_intent=repair_intent,
                ranking_hints=ranking_hints,
            )
        except TypeError:
            # 兼容旧测试桩和早期实现，避免第三期新增排序提示后把前两期基线打断
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
            repair_intent=repair_intent,
        )
        rewritten_patch_path = rewrite_meta["rewritten_patch"]
        apply_precheck_report = rewrite_meta["apply_precheck_report"]
        build_log_path = attempt_dir / "logs" / "build.log"
        route_effectiveness = build_route_effectiveness_report(
            project_root=self.runtime.project_root,
            task_id=task.task_id,
            attempt_no=attempt_no,
            current_plan=plan,
            current_patch_path=rewritten_patch_path,
            previous_attempt_dir=self._previous_attempt_dir(task_dir=task_dir, attempt_no=attempt_no),
        )
        route_effectiveness_path = write_route_effectiveness_report(
            report=route_effectiveness,
            path=attempt_dir / "rewrite" / "route_effectiveness.json",
            project_root=self.runtime.project_root,
        )

        build_precheck_path: Path | None = None
        build_summary: BuildSummary | None = None

        # apply 预检查失败不一定代表补丁本身不可用
        # target_already_patched 和 context_mismatch 都可能通过切换未修复源码基线或 reverse-unpatch 继续推进
        allow_builder_retry = self._should_retry_apply_failure_in_builder(apply_precheck_report)
        if apply_precheck_report.status == "failed" and not allow_builder_retry:
            precheck_failure_type = (
                apply_precheck_report.target_state
                or apply_precheck_report.failure_type
                or "patch_apply_failed"
            )
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
            target_state = apply_precheck_report.target_state
            attempt_record = seed_attempt_record.model_copy(
                update={
                    "candidate_id": plan.candidate_ids[0] if plan.candidate_ids else None,
                    "status": "target_state" if target_state else "failed",
                    "failure_type": precheck_failure_type,
                    "build_exec_status": apply_precheck_report.build_exec_status or "not_run",
                    "target_state": target_state,
                    "build_log_path": build_log_path,
                    "module_path": None,
                    "rewritten_patch_path": rewritten_patch_path,
                    "finished_at": datetime.now(timezone.utc),
                }
            )
            build_summary = BuildSummary(
                task_id=task.task_id,
                attempt_id=attempt_record.attempt_id,
                backend=apply_precheck_report.backend,
                builder_cmd=apply_precheck_report.command or self.build_config.kpatch_build_cmd,
                status="not_run",
                summary=apply_precheck_report.summary,
                rewritten_patch_path=rewritten_patch_path,
                source_dir=apply_precheck_report.target_source_dir,
                build_log_path=build_log_path,
                failure_type=precheck_failure_type,
                build_exec_status=apply_precheck_report.build_exec_status or "not_run",
                target_state=target_state,
            )
            attempt_record, build_summary, build_log = self._normalize_target_state_outcome(
                attempt_record=attempt_record,
                build_summary=build_summary,
                build_log=build_log,
                build_log_path=build_log_path,
            )
            self.attempt_repo.save_attempt(attempt_record)
            self.attempt_repo.save_evidence_spans(task.task_id, attempt_record.attempt_id, rewrite_evidence.spans)
            if attempt_record.status == "target_state" and attempt_record.target_state:
                failure_record = self._build_target_state_failure_record(
                    task_id=task.task_id,
                    attempt_id=attempt_record.attempt_id,
                    build_summary=build_summary,
                    build_log=build_log,
                    target_state=attempt_record.target_state,
                )
            else:
                failure_record = FailureRecord(
                    task_id=task.task_id,
                    attempt_id=attempt_record.attempt_id,
                    stage_name="build",
                    failure_type=precheck_failure_type,
                    summary=apply_precheck_report.summary,
                    evidence=[
                        item
                        for item in [apply_precheck_report.stdout, apply_precheck_report.stderr]
                        if item
                    ][:3],
                )
        else:
            attempt_record, build_log, build_precheck, build_summary = self.builder.execute_build(
                task=task,
                attempt_no=attempt_no,
                plan=plan,
                rewritten_patch_path=rewritten_patch_path,
                build_log_path=build_log_path,
            )
            attempt_record, build_summary, build_log = self._normalize_target_state_outcome(
                attempt_record=attempt_record,
                build_summary=build_summary,
                build_log=build_log,
                build_log_path=build_log_path,
            )
            attempt_record = attempt_record.model_copy(update={"started_at": seed_attempt_record.started_at})
            build_precheck_path = self.json_writer.write_model(
                build_precheck,
                attempt_dir / "artifacts" / "build_precheck.json",
            )
            self.attempt_repo.save_attempt(attempt_record)
            self.attempt_repo.save_evidence_spans(task.task_id, attempt_record.attempt_id, rewrite_evidence.spans)
            if attempt_record.status == "failed":
                failure_record = self.failure_classifier.classify_build_log(
                    task_id=task.task_id,
                    attempt_id=attempt_record.attempt_id,
                    build_log=build_log,
                    build_exec_status=build_summary.build_exec_status if build_summary is not None else None,
                    failure_type_hint=build_summary.failure_type if build_summary is not None else attempt_record.failure_type,
                    rewritten_patch_path=rewritten_patch_path,
                )
                failure_record = self._ensure_failure_specific_diagnostics(
                    failure_record=failure_record,
                    build_log=build_log,
                )
            elif attempt_record.status == "target_state" and attempt_record.target_state:
                failure_record = self._build_target_state_failure_record(
                    task_id=task.task_id,
                    attempt_id=attempt_record.attempt_id,
                    build_summary=build_summary,
                    build_log=build_log,
                    target_state=attempt_record.target_state,
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
        failure_record = self._attach_attempt_diagnostics(
            failure_record=failure_record,
            route_effectiveness=route_effectiveness,
            section_change_report_path=rewrite_meta.get("section_change_avoidance"),
            build_log=build_log,
        )
        attempt_record, build_summary, failure_record = self._maybe_mark_unresolved_kpatch_constraint(
            task=task,
            task_dir=task_dir,
            attempt_record=attempt_record,
            build_summary=build_summary,
            failure_record=failure_record,
            route_effectiveness=route_effectiveness,
        )
        self.attempt_repo.save_attempt(attempt_record)
        self.attempt_repo.save_failure_record(failure_record)
        failure_record_path = self.json_writer.write_model(failure_record, attempt_dir / "logs" / "failure_record.json")
        # builder 理论上应该总能给出 build_summary
        # 这里补一个兜底，保证后面的验证和报告还能继续读
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
                build_exec_status=attempt_record.build_exec_status,
                target_state=attempt_record.target_state,
            )
        build_summary_path = self.json_writer.write_model(
            build_summary,
            attempt_dir / "artifacts" / "build_summary.json",
        )
        failover_record_path = self._write_failover_record(attempt_dir=attempt_dir, failure_record=failure_record)

        # validator 只拿当前轮之前的历史尝试
        # 避免它在做对比时把自己这一轮还没写稳的状态也算进去
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
            """解析验证产物路径，缺失时补一个兼容占位文件"""

            # validator 的不同实现返回的产物不完全一样
            # 这里统一补齐缺失项，保证 attempt 目录结构稳定
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
            failure_context = self.assemble_context(
                stage_name="failure_analysis",
                evidence_bundle=failure_evidence,
                task=task,
                patch_bundle=patch_bundle,
                semantic_card=semantic_card,
                constraint_report=constraint_report,
                rewrite_plan=plan,
                failure_record=failure_record,
            )
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
                "termination_reason": (
                    failure_record.failure_type
                    if attempt_record.status in {"failed", "target_state"}
                    else "构建完成"
                ),
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
            ("repair_intent", repair_intent_path, "可驱动改写执行的修复意图"),
            ("route_effectiveness", route_effectiveness_path, "路线有效性检查"),
            ("environment_check_log", environment_check_path, "运行前环境一致性检查"),
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
        if rewrite_meta.get("section_change_avoidance") is not None:
            trace_artifacts.append(
                ("section_change_avoidance", rewrite_meta["section_change_avoidance"], "section change 专项收缩改写结果")
            )
        if rewrite_meta.get("semantic_guard_rewrite") is not None:
            trace_artifacts.append(
                ("semantic_guard_rewrite", rewrite_meta["semantic_guard_rewrite"], "semantic guard 专项改写结果")
            )
        if stable_baseline_preflight_path is not None:
            trace_artifacts.append(
                ("stable_baseline_preflight", stable_baseline_preflight_path, "stable source baseline 前置检查结果")
            )
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
            ("repair_intent", repair_intent_path),
            ("route_effectiveness", route_effectiveness_path),
            ("rewritten_patch", rewritten_patch_path),
            ("rewrite_reason", rewrite_meta["rewrite_reason"]),
            ("transformation_trace", rewrite_meta["transformation_trace"]),
            ("apply_precheck", rewrite_meta["apply_precheck"]),
            ("semantic_guard_rewrite", rewrite_meta.get("semantic_guard_rewrite")),
            ("section_change_avoidance", rewrite_meta.get("section_change_avoidance")),
            ("environment_check_log", environment_check_path),
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
            "build_exec_status": attempt_record.build_exec_status,
            "target_state": attempt_record.target_state,
            "build_log_path": to_project_relative(self.runtime.project_root, attempt_record.build_log_path),
            "trace_path": to_project_relative(self.runtime.project_root, trace_path),
            "failure_record_path": to_project_relative(self.runtime.project_root, failure_record_path),
            "route_effectiveness_path": to_project_relative(self.runtime.project_root, route_effectiveness_path),
            "failover_record_path": to_project_relative(self.runtime.project_root, failover_record_path),
        }


class ReportService(CoordinatorSupport):
    """负责最终报告阶段的任务编排"""

    def run(self, task_id: str) -> dict[str, Any]:
        """生成最终 JSON 和 Markdown 报告"""

        task = self.require_task(task_id)
        task_dir = self.workspace_guard.create_task_workspace(task)
        self.workspace_guard.ensure_report_workspace(task_dir)
        attempts = self.attempt_repo.list_attempts(task_id)
        artifacts = self.artifact_repo.list_artifacts(task_id)
        bootstrap_manifest = self.build_bootstrap_manifest()
        evaluation_summary = self.evaluator.summarize(attempts=attempts, artifacts=artifacts)

        # 报告优先引用分析阶段和最新 attempt 的关键产物
        # 这样报告结论和状态页看到的当前结果是一致的
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

        report.key_paths["report_json"] = to_project_relative(self.runtime.project_root, task_dir / "reports" / "report.json")
        report.key_paths["report_md"] = to_project_relative(self.runtime.project_root, task_dir / "reports" / "report.md")
        report.replay_summary["evaluation_summary_path"] = to_project_relative(self.runtime.project_root, task_dir / "reports" / "evaluation_summary.json")
        json_path = self.json_writer.write_model(report, task_dir / "reports" / "report.json")
        md_path = self.md_writer.write_report(report, task_dir / "reports" / "report.md")
        evaluation_summary_path = task_dir / "reports" / "evaluation_summary.json"
        evaluation_summary_path.write_text(
            json.dumps(relativize_payload(evaluation_summary, self.runtime.project_root), ensure_ascii=False, indent=2) + "\n",
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
            "report_json": to_project_relative(self.runtime.project_root, json_path),
            "report_md": to_project_relative(self.runtime.project_root, md_path),
            "status": "ok",
        }


class ReplayService(CoordinatorSupport):
    """负责回放阶段的任务编排"""

    def run(self, task_id: str) -> dict[str, Any]:
        """输出任务最近一轮的回放信息"""

        task = self.require_task(task_id)
        task_dir = self.workspace_guard.create_task_workspace(task)
        # replay 只做读取，不改任务状态
        # 它依赖 attempts、trace 和报告三层数据拼出最后一轮摘要
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
