"""候选排序器"""

from __future__ import annotations

from patchweaver.models.rewrite import RewriteCandidate


class CandidateRanker:
    """负责结合风险、代价和经验提示对候选排序"""

    def rank(
        self,
        candidates: list[RewriteCandidate],
        *,
        ranking_hints: dict[str, object] | None = None,
    ) -> list[RewriteCandidate]:
        """返回按综合得分降序排好的候选列表"""

        recipe_stats = (ranking_hints or {}).get("recipe_stats") or {}
        failure_pressure = (ranking_hints or {}).get("failure_pressure") or {}

        scored: list[RewriteCandidate] = []
        for candidate in candidates:
            recipe_stat = recipe_stats.get(candidate.recipe_name) or {}
            history_success_rate = float(recipe_stat.get("success_rate", 0.0))

            # 高频风险命中越多，说明这条路径更可能再次踩坑，排序时要适当降权
            pressure = 0.0
            for rule_hit in candidate.rule_hits:
                pressure += float(failure_pressure.get(rule_hit, 0))
            pressure = min(1.0, pressure / 5.0)

            score = (
                0.42 * (1.0 - candidate.expected_risk)
                + 0.18 * (1.0 - candidate.expected_semantic_drift)
                + 0.14 * (1.0 - candidate.expected_build_cost)
                + 0.20 * history_success_rate
                - 0.06 * pressure
            )

            reasons = [
                f"预估风险 {candidate.expected_risk:.2f}",
                f"语义漂移 {candidate.expected_semantic_drift:.2f}",
                f"构建代价 {candidate.expected_build_cost:.2f}",
            ]
            if history_success_rate > 0:
                reasons.append(f"历史成功率 {history_success_rate:.0%}")
            if pressure > 0:
                reasons.append(f"同类失败压力 {pressure:.2f}")

            scored.append(
                candidate.model_copy(
                    update={
                        "history_success_rate": history_success_rate,
                        "failure_pressure": pressure,
                        "ranking_score": round(score, 4),
                        "ranking_reasons": reasons,
                    }
                )
            )

        return sorted(
            scored,
            key=lambda item: (
                item.ranking_score,
                -item.expected_risk,
                -item.expected_semantic_drift,
                -item.expected_build_cost,
            ),
            reverse=True,
        )
