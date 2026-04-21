"""联合规划骨架"""

from __future__ import annotations

from patchweaver.models.constraint import ConstraintReport
from patchweaver.models.rewrite import RewriteCandidate, RewritePlan
from patchweaver.models.semantic import SemanticCard
from patchweaver.planner.candidate_ranker import CandidateRanker
from patchweaver.planner.primitive_selector import PrimitiveSelector


class JointPlanner:
    """负责组合候选改写方案，并给出最终选择"""

    def __init__(self) -> None:
        """初始化原语选择和排序组件"""

        self.primitive_selector = PrimitiveSelector()
        self.candidate_ranker = CandidateRanker()

    def plan(
        self,
        *,
        task_id: str,
        semantic_card: SemanticCard,
        constraint_report: ConstraintReport,
        ranking_hints: dict[str, object] | None = None,
    ) -> RewritePlan:
        """根据语义卡片、约束结果和经验提示生成本轮规划"""

        primitives = self.primitive_selector.select(constraint_report)
        target_files = list(dict.fromkeys(semantic_card.touched_files or semantic_card.touched_functions))
        target_functions = list(dict.fromkeys(semantic_card.touched_functions)) or target_files
        rule_hits = [item.risk_type for item in constraint_report.risk_items] or ["direct_apply_ready"]
        high_risk = max(1, constraint_report.high_risk_count) if constraint_report.risk_items else 0

        # 第一条路径优先尝试编辑半径最小的方案，适合作为主链默认入口
        candidates = [
            RewriteCandidate(
                candidate_id=f"{task_id}-candidate-001",
                recipe_name="direct_apply_patch",
                primitives=["direct_apply"],
                target_functions=target_functions,
                rule_hits=["direct_apply_ready"],
                expected_risk=0.08 if not constraint_report.risk_items else 0.28,
                expected_semantic_drift=0.04,
                expected_build_cost=0.08,
            )
        ]

        if constraint_report.risk_items:
            # 第二条路径保守一点，把高风险约束交给 wrapper 路线兜住
            candidates.append(
                RewriteCandidate(
                    candidate_id=f"{task_id}-candidate-002",
                    recipe_name="minimal_livepatch_wrap",
                    primitives=primitives,
                    target_functions=target_functions,
                    rule_hits=rule_hits,
                    expected_risk=min(0.65, 0.18 + high_risk * 0.11),
                    expected_semantic_drift=0.14,
                    expected_build_cost=0.24,
                )
            )

            # 第三条路径在原有 wrapper 基础上再加一层回调或 shadow state，专门留给高风险场景
            guarded_primitives = list(primitives)
            if constraint_report.requires_callback and "callback" not in guarded_primitives:
                guarded_primitives.append("callback")
            if constraint_report.requires_shadow_variable and "shadow_variable" not in guarded_primitives:
                guarded_primitives.append("shadow_variable")
            if guarded_primitives != primitives:
                candidates.append(
                    RewriteCandidate(
                        candidate_id=f"{task_id}-candidate-003",
                        recipe_name="minimal_livepatch_wrap",
                        primitives=guarded_primitives,
                        target_functions=target_functions,
                        rule_hits=rule_hits,
                        expected_risk=min(0.58, 0.16 + high_risk * 0.09),
                        expected_semantic_drift=0.18,
                        expected_build_cost=0.3,
                    )
                )

        ranked = self.candidate_ranker.rank(candidates, ranking_hints=ranking_hints)
        selected = ranked[0]

        selection_notes = [
            semantic_card.root_cause or "根因待后续补充。",
            f"候选数: {len(ranked)}",
            f"命中规则: {', '.join(selected.rule_hits)}",
        ]
        if selected.ranking_reasons:
            selection_notes.append("排序依据: " + "；".join(selected.ranking_reasons))

        return RewritePlan(
            task_id=task_id,
            plan_id=f"{task_id}-plan-001",
            candidate_ids=[item.candidate_id for item in ranked],
            selected_recipe=selected.recipe_name,
            selected_primitives=selected.primitives,
            target_files=target_files,
            rule_hits=selected.rule_hits,
            risk_coverage=1.0 if constraint_report.risk_items else 0.0,
            selection_reason=(
                f"优先选择综合得分最高的候选，当前命中 {selected.recipe_name}，"
                f"排序得分 {selected.ranking_score:.3f}。"
            ),
            notes=selection_notes,
            candidate_summaries=ranked,
        )
