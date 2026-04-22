"""上下文检索器"""

from __future__ import annotations

from patchweaver.models.evidence import EvidenceBundle


class ContextRetriever:
    """负责从已有证据中挑选上下文候选"""

    STAGE_HINTS = {
        "retrieval": ("patch_bundle", "source_evidence", "normalized", "raw_patch"),
        "semantic_card": ("patch_bundle", "normalized", "source_evidence", "raw_patch"),
        "constraint_diagnosis": ("semantic_card", "patch_bundle", "normalized", "source_evidence"),
        "rewrite_recipe": ("rewrite_plan", "constraint_report", "semantic_card", "patch_bundle"),
        "failure_analysis": ("failure_record", "build", "apply_precheck", "rewrite_plan"),
        "validation": ("validation_report", "semantic_precheck", "failure_record", "build_summary"),
        "reporting": ("report", "validation_report", "failure_record", "rewrite_plan"),
    }

    def select(
        self,
        bundle: EvidenceBundle,
        *,
        stage_name: str,
        max_evidence: int = 8,
        max_memory_hits: int = 3,
    ) -> EvidenceBundle:
        """按阶段偏好和预算裁剪证据"""

        hints = self.STAGE_HINTS.get(stage_name, ())
        ranked = sorted(
            bundle.spans,
            key=lambda span: (
                self._hint_score(span.source_path, hints),
                span.score,
                len(span.excerpt),
            ),
            reverse=True,
        )
        selected_spans = ranked[:max(1, max_evidence)]
        selected_memory = list(dict.fromkeys(bundle.memory_hits))[:max(0, max_memory_hits)]
        return bundle.model_copy(
            update={
                "spans": selected_spans,
                "evidence_ids": [span.evidence_id for span in selected_spans],
                "memory_hits": selected_memory,
            }
        )

    def _hint_score(self, source_path: str, hints: tuple[str, ...]) -> int:
        """计算阶段命中权重"""

        lowered = source_path.lower()
        for index, hint in enumerate(hints):
            if hint in lowered:
                return len(hints) - index
        return 0
