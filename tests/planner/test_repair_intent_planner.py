from __future__ import annotations

from patchweaver.models.constraint import ConstraintReport, RouteHint
from patchweaver.models.semantic import RepairIntent, SemanticCard
from patchweaver.planner.joint_planner import JointPlanner


def test_joint_planner_promotes_semantic_guard_when_repair_intent_requires_it() -> None:
    semantic_card = SemanticCard(
        bug_class="bounds_check",
        root_cause="入口缺少长度边界检查",
        touched_files=["fs/demo.c"],
        touched_functions=["demo_parse"],
    )
    constraint_report = ConstraintReport(
        task_id="TASK-SEMANTIC-GUARD-001",
        target_files=["fs/demo.c"],
        target_functions=["demo_parse"],
        dominant_risk_types=["guardable_memory_safety"],
        candidate_routes=["direct_apply_patch", "minimal_livepatch_wrap"],
        route_hints=[
            RouteHint(
                route_name="direct_apply_patch",
                summary="约束层认为 direct apply 可行，保留为强对照路线",
                recommended_primitives=["direct_apply"],
                blocking_risk_types=["guardable_memory_safety"],
                preferred=True,
            )
        ],
        preferred_route="direct_apply_patch",
        high_risk_count=1,
        direct_apply_viable=True,
        summary="官方 patch 可应用，但更适合收缩为函数局部 guard",
    )
    repair_intent = RepairIntent(
        cve_id="CVE-TEST-0004",
        bug_class="bounds_check",
        guard_conditions=["len > PAGE_SIZE"],
        guard_sites=["demo_parse"],
        safe_exits=["return -EINVAL;"],
        recommended_strategy="semantic_guard",
        confidence=0.8,
    )

    plan = JointPlanner().plan(
        task_id="TASK-SEMANTIC-GUARD-001",
        semantic_card=semantic_card,
        constraint_report=constraint_report,
        repair_intent=repair_intent,
    )

    assert plan.selected_recipe == "semantic_guard_rewrite"
    assert plan.selected_route_family == "semantic_guard"
    assert plan.selected_execution_mode == "semantic_guard"
    assert "semantic_guard" in plan.selected_primitives
    assert any(item.recipe_name == "semantic_guard_rewrite" for item in plan.candidate_summaries)
    assert any("修复意图策略: semantic_guard" in item for item in plan.notes)
