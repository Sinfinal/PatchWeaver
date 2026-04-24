from __future__ import annotations

from patchweaver.models.constraint import ConstraintReport, RiskItem, RouteHint
from patchweaver.models.semantic import SemanticCard
from patchweaver.planner.joint_planner import JointPlanner


def test_joint_planner_uses_memory_hints_to_rank_candidates() -> None:
    semantic_card = SemanticCard(
        root_cause="需要避开缺失 fentry 的直接替换路径。",
        touched_functions=["kernel/livepatch/demo.c"],
        must_keep_conditions=["demo_fentry_target: ctx->ready && fentry_enabled"],
    )
    constraint_report = ConstraintReport(
        task_id="TASK-PLANNER-001",
        target_files=["kernel/livepatch/demo.c"],
        target_functions=["demo_fentry_target"],
        risk_items=[
            RiskItem(
                risk_type="no_fentry_target",
                severity="high",
                required_primitives=["wrapper", "callback"],
            )
        ],
        dominant_risk_types=["no_fentry_target"],
        suggested_primitives=["wrapper", "callback"],
        forbidden_actions=["direct_trampoline_injection"],
        route_hints=[
            RouteHint(
                route_name="callback_livepatch_wrap",
                summary="当前已命中 no_fentry_target，优先走包装与回调路线",
                recommended_primitives=["wrapper", "callback"],
                blocking_risk_types=["no_fentry_target"],
                preferred=True,
            ),
            RouteHint(
                route_name="direct_apply_patch",
                summary="保留 direct apply 作为对照路径，但不作为首选",
                recommended_primitives=["direct_apply"],
                blocking_risk_types=["no_fentry_target"],
                preferred=False,
            ),
        ],
        candidate_routes=["callback_livepatch_wrap", "minimal_livepatch_wrap", "direct_apply_patch"],
        preferred_route="callback_livepatch_wrap",
        high_risk_count=1,
        requires_callback=True,
        summary="目标函数缺少稳定 fentry 入口，优先走包装与回调路线",
    )
    ranking_hints = {
        "recipe_stats": {
            "minimal_livepatch_wrap": {
                "attempts": 4,
                "success_rate": 0.75,
                "failure_rate": 0.25,
                "last_status": "built",
                "last_summary": "历史上更稳。",
                "risk_types": ["no_fentry_target"],
            }
        },
        "failure_pressure": {
            "no_fentry_target": 1,
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
    assert any("路线提示:" in item for item in plan.notes)
    assert any("约束首选路线:" in item for item in plan.notes)
    assert any("候选路线:" in item for item in plan.notes)
    assert any("禁止动作:" in item for item in plan.notes)
    assert any("关键条件:" in item for item in plan.notes)
    assert plan.selected_route_family == "wrapper"
    assert plan.selected_execution_mode == "template_wrap"


def test_joint_planner_expands_complex_routes_into_competing_candidates() -> None:
    semantic_card = SemanticCard(
        root_cause="需要改写回调路径并补齐 shadow state",
        touched_files=["kernel/livepatch/demo.c"],
        touched_functions=["demo_shadow_target"],
    )
    constraint_report = ConstraintReport(
        task_id="TASK-PLANNER-002",
        target_files=["kernel/livepatch/demo.c"],
        target_functions=["demo_shadow_target"],
        dominant_risk_types=["struct_layout_change", "no_fentry_target"],
        candidate_routes=["callback_livepatch_wrap", "shadow_state_wrap", "smpl_primary"],
        preferred_route="shadow_state_wrap",
        high_risk_count=2,
        requires_callback=True,
        requires_shadow_variable=True,
        direct_apply_viable=False,
        summary="需要在 callback 与 shadow 路线之间做取舍",
    )

    plan = JointPlanner().plan(
        task_id="TASK-PLANNER-002",
        semantic_card=semantic_card,
        constraint_report=constraint_report,
    )

    families = {item.route_family for item in plan.candidate_summaries}
    recipes = {item.recipe_name for item in plan.candidate_summaries}

    assert "callback" in families
    assert "shadow_variable" in families
    assert "smpl_primary" in families
    assert "direct_apply_patch" in recipes
    assert any(item.requires_kernel_scaffold for item in plan.candidate_summaries if item.route_family in {"callback", "shadow_variable"})


def test_joint_planner_keeps_state_preserving_route_distinct() -> None:
    semantic_card = SemanticCard(
        root_cause="结构布局变化需要显式的状态迁移路线",
        touched_files=["include/linux/demo.h"],
        touched_functions=["demo_state_apply"],
    )
    constraint_report = ConstraintReport(
        task_id="TASK-PLANNER-003",
        target_files=["include/linux/demo.h"],
        target_functions=["demo_state_apply"],
        dominant_risk_types=["struct_layout_change", "header_abi_change"],
        candidate_routes=["state_preserving_wrap", "shadow_variable_wrap", "minimal_livepatch_wrap"],
        preferred_route="state_preserving_wrap",
        high_risk_count=2,
        requires_shadow_variable=True,
        direct_apply_viable=False,
        summary="结构布局变化时优先保留状态迁移路线",
    )

    plan = JointPlanner().plan(
        task_id="TASK-PLANNER-003",
        semantic_card=semantic_card,
        constraint_report=constraint_report,
    )

    recipes = {item.recipe_name for item in plan.candidate_summaries}
    families = {item.route_family for item in plan.candidate_summaries}

    assert "state_preserving_wrap" in recipes
    assert "shadow_variable_wrap" in recipes
    assert "state_preserving" in families
    assert any(
        item.requires_kernel_scaffold and item.route_family == "state_preserving"
        for item in plan.candidate_summaries
    )


def test_joint_planner_selects_callback_recipe_when_callback_route_is_preferred() -> None:
    semantic_card = SemanticCard(
        root_cause="目标路径依赖 fentry 入口，需要保留 callback 路线",
        touched_files=["kernel/livepatch/demo.c"],
        touched_functions=["demo_callback_target"],
    )
    constraint_report = ConstraintReport(
        task_id="TASK-PLANNER-004",
        target_files=["kernel/livepatch/demo.c"],
        target_functions=["demo_callback_target"],
        dominant_risk_types=["no_fentry_target"],
        suggested_primitives=["callback", "direct_apply", "wrapper"],
        candidate_routes=["callback_livepatch_wrap", "minimal_livepatch_wrap", "direct_apply_patch"],
        preferred_route="callback_livepatch_wrap",
        high_risk_count=1,
        requires_callback=True,
        direct_apply_viable=True,
        summary="当前应优先尝试 callback 路线",
    )

    plan = JointPlanner().plan(
        task_id="TASK-PLANNER-004",
        semantic_card=semantic_card,
        constraint_report=constraint_report,
    )

    assert plan.selected_recipe == "callback_livepatch_wrap"
    assert plan.selected_route_family == "callback"
    assert plan.requires_kernel_scaffold is True


def test_joint_planner_selects_shadow_recipe_when_shadow_route_is_preferred() -> None:
    semantic_card = SemanticCard(
        root_cause="目标路径新增静态状态，需要保留 shadow_variable 路线",
        touched_files=["kernel/livepatch/demo.c"],
        touched_functions=["demo_shadow_target"],
    )
    constraint_report = ConstraintReport(
        task_id="TASK-PLANNER-005",
        target_files=["kernel/livepatch/demo.c"],
        target_functions=["demo_shadow_target"],
        dominant_risk_types=["global_data_change", "static_local_change"],
        suggested_primitives=["direct_apply", "shadow_variable", "wrapper"],
        candidate_routes=["shadow_variable_wrap", "minimal_livepatch_wrap", "direct_apply_patch"],
        preferred_route="shadow_variable_wrap",
        high_risk_count=1,
        requires_shadow_variable=True,
        direct_apply_viable=True,
        summary="当前应优先尝试 shadow_variable 路线",
    )

    plan = JointPlanner().plan(
        task_id="TASK-PLANNER-005",
        semantic_card=semantic_card,
        constraint_report=constraint_report,
    )

    assert plan.selected_recipe == "shadow_variable_wrap"
    assert plan.selected_route_family == "shadow_variable"
    assert plan.requires_kernel_scaffold is True


def test_joint_planner_selects_callback_shadow_recipe_when_shadow_and_callback_are_both_required() -> None:
    semantic_card = SemanticCard(
        root_cause="当前路径既缺稳定 fentry 落点，又需要补齐 shadow state",
        touched_files=["kernel/livepatch/demo.c"],
        touched_functions=["demo_callback_shadow_target"],
    )
    constraint_report = ConstraintReport(
        task_id="TASK-PLANNER-006",
        target_files=["kernel/livepatch/demo.c"],
        target_functions=["demo_callback_shadow_target"],
        dominant_risk_types=["no_fentry_target", "global_data_change", "static_local_change"],
        suggested_primitives=["wrapper", "callback", "shadow_variable"],
        candidate_routes=[
            "callback_shadow_wrap",
            "callback_livepatch_wrap",
            "shadow_variable_wrap",
            "minimal_livepatch_wrap",
        ],
        preferred_route="callback_shadow_wrap",
        high_risk_count=2,
        requires_callback=True,
        requires_shadow_variable=True,
        direct_apply_viable=False,
        summary="当前应优先尝试 callback_shadow 路线",
    )

    plan = JointPlanner().plan(
        task_id="TASK-PLANNER-006",
        semantic_card=semantic_card,
        constraint_report=constraint_report,
    )

    assert plan.selected_recipe == "callback_shadow_wrap"
    assert plan.selected_route_family == "callback_shadow"
    assert plan.requires_kernel_scaffold is True


def test_joint_planner_selects_smpl_primary_recipe_when_rule_prefers_structured_rewrite() -> None:
    semantic_card = SemanticCard(
        root_cause="需要优先尝试结构化变换而不是直接套 wrapper",
        touched_files=["fs/demo.c"],
        touched_functions=["demo_smpl_target"],
    )
    constraint_report = ConstraintReport(
        task_id="TASK-PLANNER-007",
        target_files=["fs/demo.c"],
        target_functions=["demo_smpl_target"],
        dominant_risk_types=["macro_control_flow_change", "error_unwind_change"],
        suggested_primitives=["wrapper", "smpl"],
        candidate_routes=["smpl_primary_rewrite", "minimal_livepatch_wrap", "direct_apply_patch"],
        preferred_route="smpl_primary_rewrite",
        high_risk_count=2,
        direct_apply_viable=False,
        summary="当前应优先尝试 SmPL 主导改写",
    )

    plan = JointPlanner().plan(
        task_id="TASK-PLANNER-007",
        semantic_card=semantic_card,
        constraint_report=constraint_report,
    )

    assert plan.selected_recipe == "smpl_primary_rewrite"
    assert plan.selected_route_family == "smpl_primary"
    assert plan.requires_kernel_scaffold is False


def test_joint_planner_deduplicates_same_route_candidates_with_different_primitive_order() -> None:
    semantic_card = SemanticCard(
        root_cause="需要确认 callback 路线只保留一份真实候选",
        touched_files=["kernel/livepatch/demo.c"],
        touched_functions=["demo_callback_target"],
    )
    constraint_report = ConstraintReport(
        task_id="TASK-PLANNER-008",
        target_files=["kernel/livepatch/demo.c"],
        target_functions=["demo_callback_target"],
        dominant_risk_types=["no_fentry_target"],
        suggested_primitives=["callback", "wrapper"],
        route_hints=[
            RouteHint(
                route_name="callback_livepatch_wrap",
                summary="缺少稳定 fentry，优先 callback 路线",
                recommended_primitives=["callback", "wrapper"],
                blocking_risk_types=["no_fentry_target"],
                preferred=True,
            ),
            RouteHint(
                route_name="direct_apply_patch",
                summary="保留 direct apply 对照路径",
                recommended_primitives=["direct_apply"],
                blocking_risk_types=["no_fentry_target"],
                preferred=False,
            ),
        ],
        candidate_routes=["callback_livepatch_wrap", "minimal_livepatch_wrap", "direct_apply_patch"],
        preferred_route="callback_livepatch_wrap",
        high_risk_count=1,
        requires_callback=True,
        direct_apply_viable=True,
        summary="需要验证候选去重稳定性",
    )

    plan = JointPlanner().plan(
        task_id="TASK-PLANNER-008",
        semantic_card=semantic_card,
        constraint_report=constraint_report,
    )

    callback_candidates = [item for item in plan.candidate_summaries if item.recipe_name == "callback_livepatch_wrap"]

    assert len(callback_candidates) == 1
    assert len(plan.candidate_summaries) == len(
        {(item.recipe_name, tuple(item.primitives)) for item in plan.candidate_summaries}
    )
