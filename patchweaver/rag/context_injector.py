"""RAG context injection for task stages"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
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
        self.project_root = Path(__file__).resolve().parents[2]

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
            return self._inject_experience_fallback(
                stage_name=stage_name,
                evidence_bundle=evidence_bundle,
                query=query,
                subsystem=subsystem,
                error=f"vector_error: {str(exc)[:200]}",
            )

        items = [item for item in result.get("items", []) if isinstance(item, dict)]
        if not items:
            return self._inject_experience_fallback(
                stage_name=stage_name,
                evidence_bundle=evidence_bundle,
                query=query,
                subsystem=subsystem,
                error="no_vector_hits",
            )

        return self._append_items(
            stage_name=stage_name,
            evidence_bundle=evidence_bundle,
            items=items,
            subsystem=subsystem,
            fallback_error=None,
        )

    def _append_items(
        self,
        *,
        stage_name: str,
        evidence_bundle: EvidenceBundle,
        items: list[dict[str, Any]],
        subsystem: str | None,
        fallback_error: str | None,
    ) -> RagInjectionResult:
        """Append retrieved items as evidence spans"""

        existing_ids = set(evidence_bundle.evidence_ids)
        added_ids: list[str] = []
        added_spans: list[EvidenceSpan] = []
        for index, item in enumerate(items, start=1):
            source_kind = str(item.get("source_kind") or "rag").upper()
            evidence_id = f"{source_kind}-{stage_name}-{index:02d}"
            if evidence_id in existing_ids:
                continue
            excerpt = self._item_excerpt(item)
            if not excerpt:
                continue
            added_ids.append(evidence_id)
            added_spans.append(
                EvidenceSpan(
                    evidence_id=evidence_id,
                    source_type=str(item.get("source_kind") or "rag"),
                    source_path=str(item.get("source_path") or item.get("url") or item.get("cve_id") or ""),
                    excerpt=excerpt,
                    start_line=None,
                    end_line=None,
                    score=float(item.get("score") or item.get("rerank_score") or item.get("vector_score") or 0.0),
                )
            )

        if not added_spans:
            return RagInjectionResult(evidence_bundle=evidence_bundle, subsystem=subsystem, error=fallback_error or "empty_rag_spans")

        return RagInjectionResult(
            evidence_bundle=evidence_bundle.model_copy(
                update={
                    "evidence_ids": list(evidence_bundle.evidence_ids) + added_ids,
                    "spans": list(evidence_bundle.spans) + added_spans,
                }
            ),
            added_count=len(added_spans),
            subsystem=subsystem,
            error=fallback_error,
        )

    def _inject_experience_fallback(
        self,
        *,
        stage_name: str,
        evidence_bundle: EvidenceBundle,
        query: str,
        subsystem: str | None,
        error: str,
    ) -> RagInjectionResult:
        """Fallback to local challenge experience fixtures when vector retrieval is unavailable"""

        if not bool(getattr(self.config, "experience_enabled", False)):
            return RagInjectionResult(evidence_bundle=evidence_bundle, subsystem=subsystem, error=error)
        items = self._search_experience(query=query, subsystem=subsystem)
        if not items:
            return RagInjectionResult(evidence_bundle=evidence_bundle, subsystem=subsystem, error=f"{error}; no_experience_hits")
        return self._append_items(
            stage_name=stage_name,
            evidence_bundle=evidence_bundle,
            items=items,
            subsystem=subsystem,
            fallback_error=f"{error}; experience_fallback",
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

    def _search_experience(self, *, query: str, subsystem: str | None) -> list[dict[str, Any]]:
        """Search local confirmed positive and kpatch constraint experience records"""

        fixture_paths = list(getattr(self.config, "experience_fixture_paths", []) or [])
        limit = int(getattr(self.config, "experience_limit", 4) or 4)
        query_lower = query.lower()
        scored: list[tuple[float, dict[str, Any]]] = []
        for fixture_path in fixture_paths:
            path = Path(str(fixture_path))
            if not path.is_absolute():
                path = self.project_root / path
            if not path.exists():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, list):
                continue
            for item in payload:
                if not isinstance(item, dict):
                    continue
                score = self._experience_score(item=item, query_lower=query_lower, subsystem=subsystem)
                if score <= 0:
                    continue
                scored.append(
                    (
                        score,
                        {
                            "source_kind": "rag_experience",
                            "source_path": str(path),
                            "score": score,
                            "cve_id": item.get("cve_id"),
                            "summary": self._experience_excerpt(item),
                            "metadata": item,
                        },
                    )
                )
        scored.sort(key=lambda value: value[0], reverse=True)
        return [item for _, item in scored[:limit]]

    def _experience_score(self, *, item: dict[str, Any], query_lower: str, subsystem: str | None) -> float:
        """Score one local experience record against the current task query"""

        haystack_parts = [
            item.get("cve_id"),
            item.get("sample_bucket"),
            item.get("screening_tier"),
            item.get("fixture_group"),
            item.get("observed_constraint"),
            item.get("expected_outcome"),
            item.get("breakthrough_status"),
            item.get("breakthrough_strategy"),
            " ".join(str(value) for value in item.get("target_modules") or []),
        ]
        haystack = " ".join(str(part) for part in haystack_parts if part).lower()
        score = 0.0
        for token in query_lower.split():
            if len(token) < 4:
                continue
            if token in haystack:
                score += 0.1
        if subsystem and subsystem.lower() in haystack:
            score += 0.35
        if item.get("screening_tier") == "positive_acceptance_confirmed":
            score += 0.25
        if item.get("sample_bucket") == "kpatch_constraint":
            score += 0.18
        if item.get("breakthrough_status"):
            score += 0.3
        return round(min(score, 1.0), 4)

    def _experience_excerpt(self, item: dict[str, Any]) -> str:
        """Render one local experience record as a compact evidence excerpt"""

        fields = [
            f"cve={item.get('cve_id')}",
            f"bucket={item.get('sample_bucket')}",
            f"tier={item.get('screening_tier')}",
            f"strategy={item.get('breakthrough_strategy') or item.get('expected_outcome')}",
            f"constraint={item.get('observed_constraint')}",
            f"modules={','.join(str(value) for value in item.get('target_modules') or [])}",
        ]
        return "; ".join(part for part in fields if not part.endswith("=None") and not part.endswith("="))
