"""联合规划骨架。"""

from __future__ import annotations

from patchweaver.models.constraint import ConstraintReport
from patchweaver.models.rewrite import RewriteCandidate, RewritePlan
from patchweaver.models.semantic import SemanticCard
from patchweaver.planner.candidate_ranker import CandidateRanker
from patchweaver.planner.primitive_selector import PrimitiveSelector


class JointPlanner:
    """负责生成候选改写规划。"""

    def __init__(self) -> None:
        """初始化原语目录。"""

        self.primitive_selector = PrimitiveSelector()
        self.candidate_ranker = CandidateRanker()

    def plan(self, *, task_id: str, semantic_card: SemanticCard, constraint_report: ConstraintReport) -> RewritePlan:
        """根据语义卡片和约束报告生成真实可执行的最小规划。"""

        primitives = self.primitive_selector.select(constraint_report)
        target_files = list(dict.fromkeys(semantic_card.touched_functions))
        rule_hits = [item.risk_type for item in constraint_report.risk_items] or ["direct_apply_ready"]

        candidates = [
            RewriteCandidate(
                candidate_id=f"{task_id}-candidate-001",
                recipe_name="direct_apply_patch",
                primitives=["direct_apply"],
                target_functions=target_files,
                rule_hits=["direct_apply_ready"],
                expected_risk=0.1 if not constraint_report.risk_items else 0.3,
                expected_semantic_drift=0.05,
                expected_build_cost=0.1,
            )
        ]
        if constraint_report.risk_items:
            candidates.append(
                RewriteCandidate(
                    candidate_id=f"{task_id}-candidate-002",
                    recipe_name="minimal_livepatch_wrap",
                    primitives=primitives,
                    target_functions=target_files,
                    rule_hits=rule_hits,
                    expected_risk=max(0.2, constraint_report.high_risk_count * 0.2),
                    expected_semantic_drift=0.15,
                    expected_build_cost=0.25,
                )
            )

        ranked = self.candidate_ranker.rank(candidates)
        selected = ranked[0]
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
                "优先选择编辑半径最小、语义漂移最低且可直接输出 unified diff 的候选。"
            ),
            notes=[
                semantic_card.root_cause or "根因待后续补充。",
                f"候选数: {len(ranked)}",
                f"命中规则: {', '.join(selected.rule_hits)}",
            ],
            candidate_summaries=ranked,
        )
