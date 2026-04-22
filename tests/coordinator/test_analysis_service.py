from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from patchweaver.coordinator.services import AnalysisService, TaskRunnerServices
from patchweaver.harness.orchestrator import HarnessOrchestrator
from patchweaver.harness.workspace_guard import WorkspaceGuard
from patchweaver.models.constraint import ConstraintReport, RouteHint
from patchweaver.models.context import BootstrapManifest, ContextBundle
from patchweaver.models.evidence import EvidenceBundle
from patchweaver.models.patch import PatchBundle
from patchweaver.models.prompt import PromptPacket
from patchweaver.models.semantic import SemanticCard, SemanticCardEnrichmentTrace
from patchweaver.models.skill import SkillRouteDecision
from patchweaver.models.task import TaskContext
from patchweaver.reporter.json_writer import JsonWriter
from patchweaver.harness.trace_writer import TraceWriter


class _FakeTaskRepo:
    def __init__(self, task: TaskContext) -> None:
        self.task = task
        self.saved_patch_bundle: PatchBundle | None = None
        self.status_updates: list[tuple[str, str, int]] = []

    def get_task(self, task_id: str) -> TaskContext | None:
        if task_id == self.task.task_id:
            return self.task
        return None

    def save_patch_bundle(self, bundle: PatchBundle) -> PatchBundle:
        self.saved_patch_bundle = bundle
        return bundle

    def update_task_status(self, task_id: str, *, status: str, current_attempt: int) -> None:
        self.status_updates.append((task_id, status, current_attempt))


class _FakeArtifactRepo:
    def __init__(self) -> None:
        self.items: list[tuple[str, str, Path]] = []

    def add_artifact(self, *, task_id: str, artifact_type: str, artifact_path: Path) -> None:
        self.items.append((task_id, artifact_type, artifact_path))


class _FakeRetriever:
    def __init__(self, patch_text: str) -> None:
        self.patch_text = patch_text
        self.last_fetch_trace_path: Path | None = None

    def fetch_patch_bundle(self, *, task: TaskContext, raw_patch_path: Path) -> PatchBundle:
        raw_patch_path.parent.mkdir(parents=True, exist_ok=True)
        raw_patch_path.write_text(self.patch_text, encoding="utf-8")
        return PatchBundle(
            task_id=task.task_id,
            cve_id=task.cve_id,
            commit_message="demo semantic flow",
            affected_files=["kernel/demo.c"],
            raw_patch_path=raw_patch_path,
        )


class _FakePatchNormalizer:
    def normalize(self, raw_patch_path: Path, normalized_patch_path: Path) -> None:
        normalized_patch_path.parent.mkdir(parents=True, exist_ok=True)
        normalized_patch_path.write_text(raw_patch_path.read_text(encoding="utf-8"), encoding="utf-8")

    def extract_affected_files(self, patch_text: str) -> list[str]:
        return ["kernel/demo.c"]


class _FakeSemanticAnalyzer:
    def analyze(self, task: TaskContext, patch_bundle: PatchBundle) -> SemanticCard:
        return SemanticCard(
            bug_class="cve_fix",
            root_cause="draft root cause",
            must_keep_conditions=["demo_check: len < limit"],
            must_keep_side_effects=["demo_check: 条件 len < limit 命中时返回 -EINVAL"],
            touched_files=["kernel/demo.c"],
            touched_functions=["demo_check"],
        )

    def maybe_enrich(
        self,
        *,
        task: TaskContext,
        patch_bundle: PatchBundle,
        draft_card: SemanticCard,
        prompt_packet: PromptPacket,
        context_bundle: ContextBundle,
        route: SkillRouteDecision | None,
        prompt_packet_path: Path | None = None,
        source_evidence_path: Path | None = None,
    ) -> tuple[SemanticCard, SemanticCardEnrichmentTrace]:
        enriched = draft_card.model_copy(
            update={
                "root_cause": "enriched root cause",
                "must_keep_conditions": ["demo_check: len + used >= limit"],
            }
        )
        trace = SemanticCardEnrichmentTrace(
            status="applied",
            applied=True,
            merged_fields=["root_cause", "must_keep_conditions"],
            prompt_packet_path=str(prompt_packet_path) if prompt_packet_path is not None else None,
            source_evidence_path=str(source_evidence_path) if source_evidence_path is not None else None,
            draft_card=draft_card.model_dump(mode="json"),
        )
        return enriched, trace


class _FakeConstraintDiagnoser:
    def __init__(self) -> None:
        self.seen_root_causes: list[str] = []
        self.seen_sources: list[tuple[str, bool]] = []

    def diagnose(
        self,
        patch_bundle: PatchBundle,
        semantic_card: SemanticCard | None = None,
        *,
        semantic_card_source: str = "unavailable",
        semantic_card_enriched: bool = False,
    ) -> ConstraintReport:
        root_cause = semantic_card.root_cause if semantic_card is not None else "missing"
        self.seen_root_causes.append(root_cause)
        self.seen_sources.append((semantic_card_source, semantic_card_enriched))
        return ConstraintReport(
            task_id=patch_bundle.task_id,
            semantic_card_source=semantic_card_source,
            semantic_card_enriched=semantic_card_enriched,
            target_files=list(semantic_card.touched_files if semantic_card is not None else []),
            target_functions=list(semantic_card.touched_functions if semantic_card is not None else []),
            candidate_routes=["direct_apply_patch"],
            preferred_route="direct_apply_patch",
            route_hints=[
                RouteHint(
                    route_name="direct_apply_patch",
                    summary=root_cause,
                    recommended_primitives=["direct_apply"],
                    preferred=True,
                )
            ],
            direct_apply_viable=True,
            summary=root_cause,
        )


def _build_services(tmp_path: Path) -> tuple[TaskRunnerServices, _FakeConstraintDiagnoser]:
    project_root = tmp_path
    workspace_root = project_root / "workspaces"
    task = TaskContext(
        task_id="analysis-001",
        cve_id="CVE-2099-0004",
        target_kernel="6.6.102-5.2.an23.x86_64",
        workspace_dir=workspace_root / "analysis-001",
    )
    runtime = SimpleNamespace(
        project_root=project_root,
        workspace_root=workspace_root,
        data_dir=project_root / "data",
        enable_read_parallel=False,
        parallel_read_limit=1,
    )
    task_repo = _FakeTaskRepo(task)
    artifact_repo = _FakeArtifactRepo()
    constraint_diagnoser = _FakeConstraintDiagnoser()
    services = TaskRunnerServices(
        runtime=runtime,
        build_config=SimpleNamespace(),
        prompts_config=SimpleNamespace(default_prompt_profile="strict", prompt_profiles={}, bootstrap_fragment_dirs=[]),
        task_repo=task_repo,
        attempt_repo=SimpleNamespace(),
        artifact_repo=artifact_repo,
        workspace_guard=WorkspaceGuard(workspace_root, project_root),
        retriever=_FakeRetriever(
            """Subject: demo: fix guard

---
diff --git a/kernel/demo.c b/kernel/demo.c
--- a/kernel/demo.c
+++ b/kernel/demo.c
@@ -1,3 +1,3 @@ static int demo_check(struct demo_ctx *ctx)
-\tif (len < limit)
+\tif (len + used >= limit)
\t\treturn -EINVAL;
"""
        ),
        patch_normalizer=_FakePatchNormalizer(),
        semantic_analyzer=_FakeSemanticAnalyzer(),
        constraint_diagnoser=constraint_diagnoser,
        context_retriever=SimpleNamespace(),
        context_budgeter=SimpleNamespace(),
        context_assembler=SimpleNamespace(),
        bootstrap_registry=SimpleNamespace(),
        prompt_compiler=SimpleNamespace(),
        skill_router=SimpleNamespace(),
        schema_guard=SimpleNamespace(),
        policy_guard=SimpleNamespace(),
        planner=SimpleNamespace(),
        rewriter=SimpleNamespace(),
        builder=SimpleNamespace(),
        failure_classifier=SimpleNamespace(),
        validator=SimpleNamespace(),
        dual_memory=SimpleNamespace(),
        harness=HarnessOrchestrator(),
        failover_controller=SimpleNamespace(),
        evaluator=SimpleNamespace(),
        replay_harness=SimpleNamespace(),
        trace_writer=TraceWriter(project_root),
        json_writer=JsonWriter(project_root),
        md_writer=SimpleNamespace(),
        report_builder=SimpleNamespace(),
    )
    return services, constraint_diagnoser


def test_analysis_service_recomputes_constraint_report_after_semantic_enrichment(tmp_path: Path) -> None:
    services, constraint_diagnoser = _build_services(tmp_path)
    service = AnalysisService(services)

    service.build_bootstrap_manifest = lambda: BootstrapManifest(fragment_ids=["boot-01"], render_order=["boot-01"])
    evidence_bundle_calls: list[tuple[str, list[str]]] = []

    def build_evidence_bundle(*, source_paths: list[Path | None], bundle_tag: str) -> EvidenceBundle:
        normalized_paths = [str(path) for path in source_paths if path is not None]
        evidence_bundle_calls.append((bundle_tag, normalized_paths))
        return EvidenceBundle(evidence_ids=[f"{bundle_tag}-01"])

    service.build_evidence_bundle = build_evidence_bundle
    service.assemble_context = lambda *, stage_name, evidence_bundle: ContextBundle(
        evidence_ids=list(evidence_bundle.evidence_ids),
        notes=[f"stage={stage_name}"],
    )

    def materialize_stage_packet(*, stage_name: str, schema_name: str, context_bundle: ContextBundle, bootstrap_manifest: BootstrapManifest, base_dir: Path) -> dict[str, object]:
        route = SkillRouteDecision(stage_name=stage_name, selected_skill=stage_name, selection_reason=f"{stage_name} route")
        prompt = PromptPacket(
            stage_name=stage_name,
            system_prompt_version="v1",
            worker_prompt_version="v1",
            schema_name=schema_name,
            prompt_sections=[f"stage={stage_name}"],
        )
        route_path = services.json_writer.write_model(route, base_dir / "route" / f"{stage_name}_skill_route.json")
        prompt_path = services.json_writer.write_model(prompt, base_dir / "prompt" / f"{stage_name}_prompt_packet.json")
        return {
            "route": route,
            "prompt_packet": prompt,
            "route_path": route_path,
            "prompt_path": prompt_path,
        }

    service.materialize_stage_packet = materialize_stage_packet

    payload = service.run("analysis-001")

    assert constraint_diagnoser.seen_root_causes == ["enriched root cause"]
    assert constraint_diagnoser.seen_sources == [("enriched", True)]
    semantic_card_payload = json.loads((tmp_path / "workspaces" / "analysis-001" / "analysis" / "semantic_card.json").read_text(encoding="utf-8"))
    constraint_report_payload = json.loads((tmp_path / "workspaces" / "analysis-001" / "analysis" / "constraint_report.json").read_text(encoding="utf-8"))
    evidence_bundle_payload = json.loads((tmp_path / "workspaces" / "analysis-001" / "analysis" / "context" / "evidence_bundle.json").read_text(encoding="utf-8"))
    context_bundle_payload = json.loads((tmp_path / "workspaces" / "analysis-001" / "analysis" / "context" / "context_bundle.json").read_text(encoding="utf-8"))

    assert semantic_card_payload["root_cause"] == "enriched root cause"
    assert semantic_card_payload["must_keep_conditions"] == ["demo_check: len + used >= limit"]
    assert constraint_report_payload["summary"] == "enriched root cause"
    assert constraint_report_payload["semantic_card_source"] == "enriched"
    assert constraint_report_payload["semantic_card_enriched"] is True
    assert context_bundle_payload["notes"] == ["stage=constraint_diagnosis"]
    assert any(bundle_tag == "ANL-SEM" for bundle_tag, _paths in evidence_bundle_calls)
    assert any(bundle_tag == "ANL-RTV" for bundle_tag, _paths in evidence_bundle_calls)
    final_bundle_paths = next(paths for bundle_tag, paths in evidence_bundle_calls if bundle_tag == "ANL")
    assert all("constraint_report.json" not in path for path in final_bundle_paths)
    assert any("semantic_card.json" in path for path in final_bundle_paths)
    assert any("source_evidence.json" in path for path in final_bundle_paths)
    assert evidence_bundle_payload["evidence_ids"] == ["ANL-01"]
    assert payload["status"] == "ok"
