from __future__ import annotations

from types import SimpleNamespace

from patchweaver.models.evidence import EvidenceBundle
from patchweaver.models.patch import PatchBundle
from patchweaver.models.task import TaskContext
from patchweaver.rag.context_injector import RagContextInjector


def test_rag_context_injector_returns_disabled_result() -> None:
    injector = RagContextInjector(SimpleNamespace(enabled=False))
    bundle = EvidenceBundle(evidence_ids=[], spans=[])

    result = injector.inject(stage_name="semantic_card", evidence_bundle=bundle)

    assert result.evidence_bundle is bundle
    assert result.added_count == 0
    assert result.error == "rag_disabled"


def test_rag_context_injector_builds_query_and_subsystem_without_search() -> None:
    injector = RagContextInjector(SimpleNamespace(enabled=False))
    task = TaskContext(
        task_id="TASK-RAG-001",
        cve_id="CVE-2024-29999",
        target_kernel="6.6.102-5.2.an23.x86_64",
        workspace_dir="workspaces/TASK-RAG-001",
    )
    patch_bundle = PatchBundle(
        task_id=task.task_id,
        cve_id=task.cve_id,
        affected_files=["drivers/net/demo.c"],
        commit_message="demo fix",
    )

    query = injector._build_query(
        stage_name="constraint_diagnosis",
        task=task,
        patch_bundle=patch_bundle,
        semantic_card=None,
        constraint_report=None,
        rewrite_plan=None,
        failure_record=None,
    )
    subsystem = injector._infer_subsystem(patch_bundle=patch_bundle, semantic_card=None)

    assert "CVE-2024-29999" in query
    assert "drivers/net/demo.c" in query
    assert subsystem == "drivers/net"


def test_rag_context_injector_falls_back_to_local_experience(tmp_path) -> None:
    fixture_path = tmp_path / "experience.json"
    fixture_path.write_text(
        """
        [
          {
            "cve_id": "CVE-2024-29999",
            "sample_bucket": "buildable_and_should_pass",
            "screening_tier": "positive_acceptance_confirmed",
            "target_modules": ["drivers/net/demo.ko"],
            "breakthrough_strategy": "call_sites_section_compat"
          }
        ]
        """,
        encoding="utf-8",
    )
    config = SimpleNamespace(
        enabled=True,
        search_limit=3,
        experience_enabled=True,
        experience_fixture_paths=[str(fixture_path)],
        experience_limit=2,
    )
    injector = RagContextInjector(config)
    task = TaskContext(
        task_id="TASK-RAG-EXP",
        cve_id="CVE-2024-29999",
        target_kernel="6.6.102-5.2.an23.x86_64",
        workspace_dir="workspaces/TASK-RAG-EXP",
    )
    patch_bundle = PatchBundle(
        task_id=task.task_id,
        cve_id=task.cve_id,
        affected_files=["drivers/net/demo.c"],
        commit_message="demo net fix",
    )

    result = injector.inject(
        stage_name="rewrite_recipe",
        evidence_bundle=EvidenceBundle(evidence_ids=[], spans=[]),
        task=task,
        patch_bundle=patch_bundle,
    )

    assert result.added_count == 1
    assert result.error and "experience_fallback" in result.error
    assert result.evidence_bundle.spans[0].source_type == "rag_experience"
    assert "call_sites_section_compat" in result.evidence_bundle.spans[0].excerpt
