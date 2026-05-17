from __future__ import annotations

from pathlib import Path

from patchweaver.config.models import RagConfig
from patchweaver.models.attempt import FailureRecord
from patchweaver.models.constraint import ConstraintReport
from patchweaver.models.evidence import EvidenceBundle, EvidenceSpan
from patchweaver.models.patch import PatchBundle
from patchweaver.models.semantic import SemanticCard
from patchweaver.models.task import TaskContext
from patchweaver.rag.context_injector import RagContextInjector


class _SearchStub:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def search(self, *, query: str, limit: int | None = None, cve_id: str | None = None, subsystem: str | None = None) -> dict:
        self.calls.append(
            {
                "query": query,
                "limit": limit,
                "cve_id": cve_id,
                "subsystem": subsystem,
            }
        )
        if cve_id == "CVE-2024-1086":
            return {"items": []}
        return {
            "items": [
                {
                    "chunk_id": "CVE-2024-1086#repair#001",
                    "cve_id": "CVE-2024-1086",
                    "section": "repair",
                    "score": 0.88,
                    "text": "Use a wrapper only when direct_apply is unsafe because nf_tables verdict validation changes control flow.",
                    "metadata": {
                        "title": "nf_tables livepatch repair card",
                        "stable_commit": "f342de4e2f33",
                        "affected_files": ["net/netfilter/nf_tables_api.c"],
                    },
                }
            ]
        }


def test_rag_context_injector_falls_back_to_global_search_and_generates_rag_spans() -> None:
    search_stub = _SearchStub()
    injector = RagContextInjector(
        RagConfig(enabled=True, search_limit=4, rerank_enabled=False),
        search_service=search_stub,
    )
    task = TaskContext(
        task_id="TASK-RAG-001",
        cve_id="CVE-2024-1086",
        target_kernel="6.6.102-5.2.an23.x86_64",
        workspace_dir=Path("workspaces/TASK-RAG-001"),
    )
    patch_bundle = PatchBundle(
        task_id=task.task_id,
        cve_id=task.cve_id,
        commit_message="netfilter: nf_tables: reject QUEUE/DROP verdict parameters",
        affected_files=["net/netfilter/nf_tables_api.c"],
    )
    semantic_card = SemanticCard(
        root_cause="positive drop error reaches nf_hook_slow and can double free verdict state",
        touched_files=["net/netfilter/nf_tables_api.c"],
        touched_functions=["nft_verdict_init", "nf_hook_slow"],
    )
    constraint_report = ConstraintReport(
        task_id=task.task_id,
        dominant_risk_types=["kpatch_constraint"],
        preferred_route="minimal_livepatch_wrap",
        target_files=["net/netfilter/nf_tables_api.c"],
        target_functions=["nft_verdict_init"],
    )
    base_bundle = EvidenceBundle(
        evidence_ids=["EV-001"],
        spans=[
            EvidenceSpan(
                evidence_id="EV-001",
                source_type="json",
                source_path="analysis/constraint_report.json",
                excerpt="constraint report excerpt",
                start_line=1,
                end_line=3,
                score=1.0,
            )
        ],
    )

    result = injector.inject(
        stage_name="rewrite_recipe",
        task=task,
        evidence_bundle=base_bundle,
        patch_bundle=patch_bundle,
        semantic_card=semantic_card,
        constraint_report=constraint_report,
    )

    assert result.error is None
    assert result.added_count == 1
    assert result.subsystem == "net"
    assert len(search_stub.calls) == 3
    assert search_stub.calls[0]["cve_id"] == "CVE-2024-1086"
    assert search_stub.calls[0]["subsystem"] == "net"
    assert search_stub.calls[1]["cve_id"] is None
    assert search_stub.calls[2]["subsystem"] is None
    assert "root cause:" in str(search_stub.calls[0]["query"])
    assert any(span.source_type == "rag" for span in result.evidence_bundle.spans)
    rag_span = [span for span in result.evidence_bundle.spans if span.source_type == "rag"][0]
    assert rag_span.source_path.startswith("rag://CVE-2024-1086/repair/")
    assert "nf_tables livepatch repair card" in rag_span.excerpt


def test_rag_context_injector_uses_failure_signals_for_failure_analysis_queries() -> None:
    search_stub = _SearchStub()
    injector = RagContextInjector(
        RagConfig(enabled=True, search_limit=3, rerank_enabled=False),
        search_service=search_stub,
    )
    task = TaskContext(
        task_id="TASK-RAG-002",
        cve_id="CVE-2024-1086",
        target_kernel="6.6.102-5.2.an23.x86_64",
        workspace_dir=Path("workspaces/TASK-RAG-002"),
    )
    failure_record = FailureRecord(
        task_id=task.task_id,
        attempt_id="TASK-RAG-002-A001",
        stage_name="build",
        failure_type="missing_fentry",
        summary="build log reports missing fentry for the rewritten entry point",
        evidence=["missing fentry entry point", "wrapper required"],
    )

    injector.inject(
        stage_name="failure_analysis",
        task=task,
        evidence_bundle=EvidenceBundle(),
        failure_record=failure_record,
    )

    assert search_stub.calls
    assert "failure type: missing_fentry" in str(search_stub.calls[0]["query"])
    assert "failure summary: build log reports missing fentry" in str(search_stub.calls[0]["query"])
