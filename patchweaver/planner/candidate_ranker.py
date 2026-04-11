"""候选排序器。"""

from __future__ import annotations

from patchweaver.models.rewrite import RewriteCandidate


class CandidateRanker:
    """负责按简单规则对候选方案排序。"""

    def rank(self, candidates: list[RewriteCandidate]) -> list[RewriteCandidate]:
        """返回按风险和语义偏移排序后的候选列表。"""

        return sorted(candidates, key=lambda item: (item.expected_risk, item.expected_semantic_drift, item.expected_build_cost))

