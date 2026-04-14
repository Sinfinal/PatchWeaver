from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from patchweaver.context.assembler import ContextAssembler
from patchweaver.context.retriever import ContextRetriever
from patchweaver.memory.dual_memory import DualMemory
from patchweaver.models.attempt import AttemptRecord, FailureRecord
from patchweaver.models.context import BootstrapManifest
from patchweaver.models.evidence import EvidenceBundle, EvidenceSpan
from patchweaver.models.rewrite import RewritePlan
from patchweaver.models.skill import SkillRouteDecision
from patchweaver.models.task import TaskContext
from patchweaver.models.validation import ValidationItem, ValidationReport
from patchweaver.prompting.compiler import PromptCompiler


def _case_dir(case_name: str) -> Path:
    base_dir = Path("E:/Desk/patchweaver_pytest_cases")
    base_dir.mkdir(parents=True, exist_ok=True)
    root = base_dir / f"{case_name}-{uuid4().hex[:8]}"
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_dual_memory_context_and_prompt_compiler_form_a_closed_loop() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    tmp_path = _case_dir("context-memory-prompt")
    dual_memory = DualMemory(tmp_path / "memory")
    task = TaskContext(
        task_id="TASK-MEM-001",
        cve_id="CVE-2099-0010",
        target_kernel="6.6.102-5.2.an23.x86_64",
        workspace_dir=tmp_path / "workspace",
    )
    plan = RewritePlan(
        task_id=task.task_id,
        plan_id=f"{task.task_id}-plan-001",
        candidate_ids=["cand-001"],
        selected_recipe="minimal_livepatch_wrap",
        selected_primitives=["wrapper"],
        rule_hits=["missing_fentry"],
        target_files=["kernel/livepatch/demo.c"],
        selection_reason="命中 fentry 风险，优先选择 wrapper。",
    )
    attempt = AttemptRecord(
        task_id=task.task_id,
        attempt_no=1,
        attempt_id=f"{task.task_id}-A001",
        candidate_id="cand-001",
        status="failed",
        failure_type="missing_fentry",
    )
    failure_record = FailureRecord(
        task_id=task.task_id,
        attempt_id=attempt.attempt_id,
        stage_name="build",
        failure_type="missing_fentry",
        summary="构建日志显示缺少稳定 fentry 入口。",
        evidence=["fentry trampoline unresolved", "wrapper required"],
    )
    validation_report = ValidationReport(
        semantic_guard_result=ValidationItem(status="failed", ok=False, detail="存在 livepatch 入口风险。")
    )

    dual_memory.record_attempt(
        task=task,
        plan=plan,
        attempt=attempt,
        failure_record=failure_record,
        validation_report=validation_report,
    )

    evidence_bundle = EvidenceBundle(
        evidence_ids=["EV-001", "EV-002"],
        spans=[
            EvidenceSpan(
                evidence_id="EV-001",
                source_type="json",
                source_path=str(tmp_path / "constraint_report.json"),
                excerpt="risk_type=missing_fentry primitive=wrapper",
                start_line=1,
                end_line=3,
                score=0.9,
            ),
            EvidenceSpan(
                evidence_id="EV-002",
                source_type="log",
                source_path=str(tmp_path / "build.log"),
                excerpt="missing fentry entry point in patched function",
                start_line=1,
                end_line=2,
                score=0.8,
            ),
        ],
    )

    memory_hits = dual_memory.recall(stage_name="rewrite_recipe", evidence_bundle=evidence_bundle, limit=3)

    assert any("RecipeMemory" in item for item in memory_hits)
    assert any("FailureMemory" in item for item in memory_hits)

    selected = ContextRetriever().select(
        evidence_bundle.model_copy(update={"memory_hits": memory_hits}),
        stage_name="rewrite_recipe",
        max_evidence=2,
        max_memory_hits=2,
    )
    context_bundle = ContextAssembler().assemble(selected)

    assert context_bundle.memory_hits == 2
    assert len(context_bundle.memory_summaries) == 2
    assert context_bundle.evidence_ids == ["EV-001", "EV-002"]

    route = SkillRouteDecision(
        stage_name="rewrite_recipe",
        candidate_skills=["rewrite_recipe"],
        selected_skill="rewrite_recipe",
        selection_reason="命中 project 级 rewrite skill。",
        readonly_subagent_allowed=False,
        contract_summary=["输入: patch_bundle.json", "输出: rewrite_plan.json"],
        fallback_used=False,
        route_source="registry",
    )
    packet = PromptCompiler(repo_root).compile(
        stage_name="rewrite_recipe",
        context_bundle=context_bundle,
        bootstrap_manifest=BootstrapManifest(fragment_ids=["system/core"], total_token_cost=42),
        schema_name="RewritePlan",
        route=route,
    )

    assert packet.stage_name == "rewrite_recipe"
    assert any("plan_id" in section for section in packet.prompt_sections)
    assert any("记忆摘要" in section for section in packet.prompt_sections)
    assert any("选中 Skill: rewrite_recipe" in section for section in packet.prompt_sections)
