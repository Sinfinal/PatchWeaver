"""RAG context injection for task stages"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from patchweaver.config.models import RagConfig
from patchweaver.models.attempt import FailureRecord
from patchweaver.models.constraint import ConstraintReport
from patchweaver.models.evidence import EvidenceBundle, EvidenceSpan
from patchweaver.models.patch import PatchBundle
from patchweaver.models.rewrite import RewritePlan
from patchweaver.models.semantic import SemanticCard
from patchweaver.models.task import TaskContext


@dataclass(slots=True)
class RagInjectionResult:
    """Result of one RAG injection attempt"""

    evidence_bundle: EvidenceBundle
    added_count: int = 0
    subsystem: str | None = None
    error: str | None = None


class RagContextInjector:
    """Inject RAG hits into the ordinary evidence bundle without blocking the main chain"""

    def __init__(self, config: RagConfig | None) -> None:
        self.config = config

    def inject(
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
    ) -> RagInjectionResult:
        """Search similar CVE context and append it as evidence spans"""

        if self.config is None or not self.config.enabled:
            return RagInjectionResult(evidence_bundle=evidence_bundle, error="rag_disabled")

        query = self._build_query(
            stage_name=stage_name,
            task=task,
            patch_bundle=patch_bundle,
            semantic_card=semantic_card,
            constraint_report=constraint_report,
            rewrite_plan=rewrite_plan,
            failure_record=failure_record,
        )
        if not query:
            return RagInjectionResult(evidence_bundle=evidence_bundle, error="empty_query")

        subsystem = self._infer_subsystem(patch_bundle=patch_bundle, semantic_card=semantic_card)
        try:
            from patchweaver.rag.search_service import RagSearchService

            result = RagSearchService(self.config).search(
                query=query,
                limit=self.config.search_limit,
                subsystem=subsystem,
            )
        except Exception as exc:  # noqa: BLE001
            return RagInjectionResult(evidence_bundle=evidence_bundle, subsystem=subsystem, error=str(exc)[:240])

        items = [item for item in result.get("items", []) if isinstance(item, dict)]
        if not items:
            return RagInjectionResult(evidence_bundle=evidence_bundle, subsystem=subsystem, error="no_rag_hits")

        existing_ids = set(evidence_bundle.evidence_ids)
        added_ids: list[str] = []
        added_spans: list[EvidenceSpan] = []
        for index, item in enumerate(items, start=1):
            evidence_id = f"RAG-{stage_name}-{index:02d}"
            if evidence_id in existing_ids:
                continue
            excerpt = self._item_excerpt(item)
            if not excerpt:
                continue
            added_ids.append(evidence_id)
            added_spans.append(
                EvidenceSpan(
                    evidence_id=evidence_id,
                    source_type="rag",
                    source_path=str(item.get("source_path") or item.get("url") or item.get("cve_id") or ""),
                    excerpt=excerpt,
                    start_line=None,
                    end_line=None,
                    score=float(item.get("score") or item.get("rerank_score") or item.get("vector_score") or 0.0),
                )
            )

        if not added_spans:
            return RagInjectionResult(evidence_bundle=evidence_bundle, subsystem=subsystem, error="empty_rag_spans")

        return RagInjectionResult(
            evidence_bundle=evidence_bundle.model_copy(
                update={
                    "evidence_ids": list(evidence_bundle.evidence_ids) + added_ids,
                    "spans": list(evidence_bundle.spans) + added_spans,
                }
            ),
            added_count=len(added_spans),
            subsystem=subsystem,
        )

    def _build_query(
        self,
        *,
        stage_name: str,
        task: TaskContext | None,
        patch_bundle: PatchBundle | None,
        semantic_card: SemanticCard | None,
        constraint_report: ConstraintReport | None,
        rewrite_plan: RewritePlan | None,
        failure_record: FailureRecord | None,
    ) -> str:
        """Build a compact retrieval query from current task state"""

        parts: list[str] = [stage_name]
        if task is not None:
            parts.extend([task.cve_id, task.target_kernel])
        if patch_bundle is not None:
            parts.extend(patch_bundle.affected_files[:8])
            if patch_bundle.commit_message:
                parts.append(patch_bundle.commit_message)
        if semantic_card is not None:
            parts.extend(getattr(semantic_card, "affected_functions", [])[:8])
            parts.extend(getattr(semantic_card, "side_effects", [])[:4])
        if constraint_report is not None:
            parts.extend(constraint_report.dominant_risk_types[:8])
        if rewrite_plan is not None and rewrite_plan.selected_recipe:
            parts.append(rewrite_plan.selected_recipe)
        if failure_record is not None:
            parts.append(failure_record.failure_type)
            parts.append(failure_record.summary)
        return " ".join(str(item) for item in parts if item)

    def _infer_subsystem(self, *, patch_bundle: PatchBundle | None, semantic_card: SemanticCard | None) -> str | None:
        """Infer a rough subsystem key for RAG filtering"""

        files: list[str] = []
        if patch_bundle is not None:
            files.extend(patch_bundle.affected_files)
        if semantic_card is not None:
            files.extend(str(item) for item in getattr(semantic_card, "affected_files", []))
        if not files:
            return None
        first = files[0].strip("/")
        parts = [part for part in first.split("/") if part]
        if len(parts) >= 2:
            return "/".join(parts[:2])
        return parts[0] if parts else None

    def _item_excerpt(self, item: dict[str, Any]) -> str:
        """Extract display text from one RAG hit"""

        text = str(item.get("text") or item.get("summary") or item.get("content") or "").strip()
        if not text:
            return ""
        return text[:1200]
