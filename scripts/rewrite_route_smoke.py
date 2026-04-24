from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from patchweaver.models.constraint import ConstraintReport
from patchweaver.models.patch import PatchBundle
from patchweaver.models.semantic import SemanticCard
from patchweaver.models.rewrite import RewritePlan
from patchweaver.planner.joint_planner import JointPlanner
from patchweaver.rewriter.executor import RewriteExecutor


class BuilderStub:
    """提供最小 builder 探针，避免烟测依赖真实源码树"""

    def probe_environment(self) -> dict[str, object]:
        """返回空源码目录，让 apply 预检查按预期 skip"""

        return {"selected_source_dir": None}


@dataclass(frozen=True)
class RewriteCase:
    """描述一条 5.5 阶段改写路线样例"""

    name: str
    relative_file: str
    semantic_function: str
    dominant_risk_types: list[str]
    suggested_primitives: list[str]
    candidate_routes: list[str]
    preferred_route: str
    high_risk_count: int
    requires_callback: bool
    requires_shadow_variable: bool
    direct_apply_viable: bool
    expected_selected_recipe: str
    expected_route_family: str
    expected_execution_mode: str
    expect_kernel_adapter: bool


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""

    parser = argparse.ArgumentParser(description="5.5 改写规划与复杂路线烟测")
    parser.add_argument("--rounds", type=int, default=5, help="连续验证轮数")
    return parser.parse_args()


def rewrite_cases() -> list[RewriteCase]:
    """返回本轮覆盖的改写路线集合"""

    return [
        RewriteCase(
            name="direct_apply",
            relative_file="fs/demo.c",
            semantic_function="demo_direct_apply",
            dominant_risk_types=[],
            suggested_primitives=["direct_apply"],
            candidate_routes=["direct_apply_patch"],
            preferred_route="direct_apply_patch",
            high_risk_count=0,
            requires_callback=False,
            requires_shadow_variable=False,
            direct_apply_viable=True,
            expected_selected_recipe="direct_apply_patch",
            expected_route_family="direct_apply",
            expected_execution_mode="direct_patch",
            expect_kernel_adapter=False,
        ),
        RewriteCase(
            name="callback",
            relative_file="kernel/livepatch/demo.c",
            semantic_function="demo_callback_target",
            dominant_risk_types=["no_fentry_target"],
            suggested_primitives=["wrapper", "callback", "direct_apply"],
            candidate_routes=["callback_livepatch_wrap", "minimal_livepatch_wrap", "direct_apply_patch"],
            preferred_route="callback_livepatch_wrap",
            high_risk_count=1,
            requires_callback=True,
            requires_shadow_variable=False,
            direct_apply_viable=True,
            expected_selected_recipe="callback_livepatch_wrap",
            expected_route_family="callback",
            expected_execution_mode="callback_scaffold",
            expect_kernel_adapter=True,
        ),
        RewriteCase(
            name="shadow_variable",
            relative_file="kernel/livepatch/demo.c",
            semantic_function="demo_shadow_target",
            dominant_risk_types=["global_data_change", "static_local_change"],
            suggested_primitives=["wrapper", "shadow_variable", "direct_apply"],
            candidate_routes=["shadow_variable_wrap", "minimal_livepatch_wrap", "direct_apply_patch"],
            preferred_route="shadow_variable_wrap",
            high_risk_count=1,
            requires_callback=False,
            requires_shadow_variable=True,
            direct_apply_viable=True,
            expected_selected_recipe="shadow_variable_wrap",
            expected_route_family="shadow_variable",
            expected_execution_mode="shadow_state_scaffold",
            expect_kernel_adapter=True,
        ),
        RewriteCase(
            name="callback_shadow",
            relative_file="kernel/livepatch/demo.c",
            semantic_function="demo_callback_shadow_target",
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
            expected_selected_recipe="callback_shadow_wrap",
            expected_route_family="callback_shadow",
            expected_execution_mode="callback_shadow_scaffold",
            expect_kernel_adapter=True,
        ),
        RewriteCase(
            name="state_preserving",
            relative_file="include/linux/demo.h",
            semantic_function="demo_state_apply",
            dominant_risk_types=["global_data_change", "header_abi_change", "static_local_change", "struct_layout_change"],
            suggested_primitives=["wrapper", "shadow_variable", "state_preserving", "direct_apply"],
            candidate_routes=["state_preserving_wrap", "shadow_variable_wrap", "minimal_livepatch_wrap", "direct_apply_patch"],
            preferred_route="state_preserving_wrap",
            high_risk_count=2,
            requires_callback=False,
            requires_shadow_variable=True,
            direct_apply_viable=True,
            expected_selected_recipe="state_preserving_wrap",
            expected_route_family="state_preserving",
            expected_execution_mode="state_preserving_scaffold",
            expect_kernel_adapter=True,
        ),
        RewriteCase(
            name="smpl_primary",
            relative_file="fs/demo.c",
            semantic_function="demo_smpl_target",
            dominant_risk_types=["macro_control_flow_change", "error_unwind_change"],
            suggested_primitives=["wrapper", "smpl"],
            candidate_routes=["smpl_primary_rewrite", "minimal_livepatch_wrap", "direct_apply_patch"],
            preferred_route="smpl_primary_rewrite",
            high_risk_count=2,
            requires_callback=False,
            requires_shadow_variable=False,
            direct_apply_viable=False,
            expected_selected_recipe="smpl_primary_rewrite",
            expected_route_family="smpl_primary",
            expected_execution_mode="smpl_primary",
            expect_kernel_adapter=False,
        ),
    ]


def make_patch(case: RewriteCase, *, round_no: int) -> Path:
    """为当前样例生成一份最小 patch"""

    root = Path(tempfile.mkdtemp(prefix=f"rewrite-route-{case.name}-{round_no:02d}-"))
    patch_path = root / "normalized.patch"
    patch_path.write_text(
        "\n".join(
            [
                f"diff --git a/{case.relative_file} b/{case.relative_file}",
                f"--- a/{case.relative_file}",
                f"+++ b/{case.relative_file}",
                "@@ -1 +1,2 @@",
                "-return old_value;",
                "+return new_value;",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return patch_path


def make_plan(case: RewriteCase, *, round_no: int) -> RewritePlan:
    """构造本轮规划结果"""

    task_id = f"rewrite-route-{case.name}-{round_no:02d}"
    semantic_card = SemanticCard(
        bug_class="cve_fix",
        root_cause=f"{case.name} 路线验证样例",
        touched_files=[case.relative_file],
        touched_functions=[case.semantic_function],
    )
    constraint_report = ConstraintReport(
        task_id=task_id,
        target_files=[case.relative_file],
        target_functions=[case.semantic_function],
        dominant_risk_types=case.dominant_risk_types,
        suggested_primitives=case.suggested_primitives,
        candidate_routes=case.candidate_routes,
        preferred_route=case.preferred_route,
        high_risk_count=case.high_risk_count,
        requires_callback=case.requires_callback,
        requires_shadow_variable=case.requires_shadow_variable,
        direct_apply_viable=case.direct_apply_viable,
        summary=f"{case.name} 路线规划验证",
    )
    return JointPlanner().plan(
        task_id=task_id,
        semantic_card=semantic_card,
        constraint_report=constraint_report,
    )


def run_case(case: RewriteCase, *, round_no: int) -> dict[str, object]:
    """执行单条 5.5 路线验证并返回结构化结果"""

    task_id = f"rewrite-route-{case.name}-{round_no:02d}"
    plan = make_plan(case, round_no=round_no)
    patch_path = make_patch(case, round_no=round_no)
    patch_bundle = PatchBundle(
        task_id=task_id,
        cve_id="CVE-TEST-0000",
        affected_files=[case.relative_file],
        normalized_patch_path=patch_path,
    )
    rewrite_dir = patch_path.parent / "rewrite"
    outputs = RewriteExecutor(PROJECT_ROOT).execute(
        plan=plan,
        patch_bundle=patch_bundle,
        rewrite_dir=rewrite_dir,
        builder=BuilderStub(),
        task_id=task_id,
        attempt_no=1,
    )

    candidate_keys = {(item.recipe_name, tuple(item.primitives)) for item in plan.candidate_summaries}
    if len(candidate_keys) != len(plan.candidate_summaries):
        raise RuntimeError(f"{case.name} 存在重复候选: {[item.recipe_name for item in plan.candidate_summaries]}")
    if len(candidate_keys) < 2:
        raise RuntimeError(f"{case.name} 候选竞争不足: {[item.recipe_name for item in plan.candidate_summaries]}")
    if plan.selected_recipe != case.expected_selected_recipe:
        raise RuntimeError(
            f"{case.name} 期望 selected_recipe={case.expected_selected_recipe} 实际为 {plan.selected_recipe}"
        )
    if plan.selected_route_family != case.expected_route_family:
        raise RuntimeError(
            f"{case.name} 期望 route_family={case.expected_route_family} 实际为 {plan.selected_route_family}"
        )
    if plan.selected_execution_mode != case.expected_execution_mode:
        raise RuntimeError(
            f"{case.name} 期望 execution_mode={case.expected_execution_mode} 实际为 {plan.selected_execution_mode}"
        )

    trace_payload = json.loads(outputs["transformation_trace"].read_text(encoding="utf-8"))
    rewrite_reason = json.loads(outputs["rewrite_reason"].read_text(encoding="utf-8"))
    step_map = {step["engine"]: step for step in trace_payload["steps"]}
    has_kernel_adapter = outputs["kernel_adapter_plan"] is not None and outputs["kernel_adapter_plan"].exists()

    if has_kernel_adapter != case.expect_kernel_adapter:
        raise RuntimeError(
            f"{case.name} 期望 kernel_adapter={case.expect_kernel_adapter} 实际为 {has_kernel_adapter}"
        )
    if case.expected_selected_recipe not in step_map["template"]["summary"]:
        raise RuntimeError(f"{case.name} 模板层未命中预期 recipe")
    if f"{case.expected_selected_recipe}.cocci" not in step_map["smpl"]["summary"]:
        raise RuntimeError(f"{case.name} SmPL 轨迹未命中预期规则")
    if rewrite_reason["selected_recipe"] != case.expected_selected_recipe:
        raise RuntimeError(f"{case.name} rewrite_reason 记录的 recipe 不一致")

    return {
        "round": round_no,
        "case": case.name,
        "selected_recipe": plan.selected_recipe,
        "selected_route_family": plan.selected_route_family,
        "candidate_recipes": [item.recipe_name for item in plan.candidate_summaries],
        "kernel_adapter_plan": has_kernel_adapter,
        "template_summary": step_map["template"]["summary"],
        "smpl_summary": step_map["smpl"]["summary"],
        "apply_precheck_status": outputs["apply_precheck_report"].status,
    }


def main() -> int:
    """按轮执行 5.5 阶段烟测"""

    args = parse_args()
    cases = rewrite_cases()
    total = 0
    for round_no in range(1, args.rounds + 1):
        for case in cases:
            total += 1
            print(json.dumps(run_case(case, round_no=round_no), ensure_ascii=False))

    print(
        json.dumps(
            {
                "status": "passed",
                "rounds": args.rounds,
                "cases": [item.name for item in cases],
                "total_runs": total,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
