"""联合规划骨架。"""

from __future__ import annotations

from patchweaver.models.constraint import ConstraintReport
from patchweaver.models.semantic import SemanticCard
from patchweaver.models.rewrite import RewritePlan
from patchweaver.planner.primitive_catalog import PrimitiveCatalog


class JointPlanner:
    """负责生成候选改写规划。"""

    def __init__(self) -> None:
        """初始化原语目录。"""

        self.primitive_catalog = PrimitiveCatalog()

    def plan(self, *, task_id: str, semantic_card: SemanticCard, constraint_report: ConstraintReport) -> RewritePlan:
        """根据语义卡片和约束报告生成最小规划。"""

        primitives = self.primitive_catalog.suggest(constraint_report)
        return RewritePlan(
            task_id=task_id,
            plan_id=f"{task_id}-plan-001",
            candidate_ids=[f"{task_id}-candidate-001"],
            selected_recipe="mvp_placeholder",
            selected_primitives=primitives,
            risk_coverage=1.0 if constraint_report.risk_items else 0.0,
            notes=[semantic_card.root_cause or "根因待后续补充。"],
        )
