from __future__ import annotations

from patchweaver.models.constraint import ConstraintReport, RiskItem
from patchweaver.models.semantic import SemanticCard
from patchweaver.planner.joint_planner import JointPlanner


def test_joint_planner_uses_memory_hints_to_rank_candidates() -> None:
    semantic_card = SemanticCard(
        root_cause="需要避开缺失 fentry 的直接替换路径。",
        touched_functions=["kernel/livepatch/demo.c"],
    )
    constraint_report = ConstraintReport(
        task_id="TASK-PLANNER-001",
        risk_items=[
            RiskItem(
                risk_type="missing_fentry",
                severity="high",
                required_primitives=["wrapper"],
            )
        ],
        high_risk_count=1,
    )
    ranking_hints = {
        "recipe_stats": {
            "minimal_livepatch_wrap": {
                "attempts": 4,
                "success_rate": 0.75,
                "failure_rate": 0.25,
                "last_status": "built",
                "last_summary": "历史上更稳。",
                "risk_types": ["missing_fentry"],
            }
        },
        "failure_pressure": {
            "missing_fentry": 1,
        },
    }

    plan = JointPlanner().plan(
        task_id="TASK-PLANNER-001",
        semantic_card=semantic_card,
        constraint_report=constraint_report,
        ranking_hints=ranking_hints,
    )

    assert plan.selected_recipe == "minimal_livepatch_wrap"
    assert plan.candidate_summaries[0].history_success_rate == 0.75
    assert plan.candidate_summaries[0].ranking_score >= plan.candidate_summaries[-1].ranking_score
    assert any("历史成功率" in item for item in plan.candidate_summaries[0].ranking_reasons)
