"""上下文装配。"""

from __future__ import annotations

from patchweaver.context.deduper import dedupe_spans
from patchweaver.models.context import ContextBundle
from patchweaver.models.evidence import EvidenceBundle


class ContextAssembler:
    """把证据集合整理成阶段可用的上下文包。"""

    def assemble(self, evidence_bundle: EvidenceBundle) -> ContextBundle:
        """生成一份最小可用的 ContextBundle。"""

        spans, duplicate_hits = dedupe_spans(evidence_bundle.spans)
        token_cost = sum(max(1, len(span.excerpt) // 4) for span in spans)
        notes = [
            f"证据片段数: {len(spans)}",
            f"记忆命中数: {len(evidence_bundle.memory_hits)}",
        ]
        if duplicate_hits:
            notes.append(f"已抑制重复证据: {duplicate_hits}")
        return ContextBundle(
            evidence_ids=evidence_bundle.evidence_ids,
            token_cost=token_cost,
            duplicate_hits=duplicate_hits,
            memory_hits=len(evidence_bundle.memory_hits),
            source_spans=spans,
            notes=notes,
        )
