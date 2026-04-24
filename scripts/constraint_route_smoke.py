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

from patchweaver.analyzer.constraint_service import ConstraintDiagnoser
from patchweaver.models.patch import PatchBundle
from patchweaver.models.semantic import SemanticCard
from patchweaver.planner.joint_planner import JointPlanner


@dataclass(frozen=True)
class RouteCase:
    """描述一条约束路线的烟测样例"""

    name: str
    affected_files: list[str]
    patch_lines: list[str]
    semantic_function: str
    expected_preferred_route: str
    expected_candidate_recipe: str
    expected_selected_recipe: str


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""

    parser = argparse.ArgumentParser(description="约束诊断多路线烟测")
    parser.add_argument("--rounds", type=int, default=5, help="连续验证轮数")
    return parser.parse_args()


def route_cases() -> list[RouteCase]:
    """返回本轮覆盖的路线集合"""

    return [
        RouteCase(
            name="direct_apply",
            affected_files=["fs/demo.c"],
            patch_lines=[
                "diff --git a/fs/demo.c b/fs/demo.c",
                "--- a/fs/demo.c",
                "+++ b/fs/demo.c",
                "@@ -1 +1 @@",
                "-if (old_guard)",
                "+if (size + len > limit)",
            ],
            semantic_function="demo_direct_apply",
            expected_preferred_route="direct_apply_patch",
            expected_candidate_recipe="direct_apply_patch",
            expected_selected_recipe="direct_apply_patch",
        ),
        RouteCase(
            name="callback",
            affected_files=["kernel/livepatch/demo.c"],
            patch_lines=[
                "diff --git a/kernel/livepatch/demo.c b/kernel/livepatch/demo.c",
                "--- a/kernel/livepatch/demo.c",
                "+++ b/kernel/livepatch/demo.c",
                "@@ -1 +1,2 @@",
                "+void ftrace_entry_hook(void);",
                "+return invoke_ftrace_path(ctx);",
            ],
            semantic_function="demo_callback_target",
            expected_preferred_route="callback_livepatch_wrap",
            expected_candidate_recipe="callback_livepatch_wrap",
            expected_selected_recipe="callback_livepatch_wrap",
        ),
        RouteCase(
            name="shadow_variable",
            affected_files=["kernel/livepatch/demo.c"],
            patch_lines=[
                "diff --git a/kernel/livepatch/demo.c b/kernel/livepatch/demo.c",
                "--- a/kernel/livepatch/demo.c",
                "+++ b/kernel/livepatch/demo.c",
                "@@ -1 +1,2 @@",
                "+static int shadow_state = 0;",
                "+shadow_state++;",
            ],
            semantic_function="demo_shadow_target",
            expected_preferred_route="shadow_variable_wrap",
            expected_candidate_recipe="shadow_variable_wrap",
            expected_selected_recipe="shadow_variable_wrap",
        ),
        RouteCase(
            name="state_preserving",
            affected_files=["include/linux/demo.h"],
            patch_lines=[
                "diff --git a/include/linux/demo.h b/include/linux/demo.h",
                "--- a/include/linux/demo.h",
                "+++ b/include/linux/demo.h",
                "@@ -1 +1,4 @@",
                "+struct demo_state {",
                "+    int version;",
                "+};",
                "+static int global_state = 0;",
            ],
            semantic_function="demo_state_apply",
            expected_preferred_route="state_preserving_wrap",
            expected_candidate_recipe="state_preserving_wrap",
            expected_selected_recipe="state_preserving_wrap",
        ),
    ]


def make_patch(case: RouteCase, *, round_no: int) -> Path:
    """为当前样例落一份临时 patch"""

    root = Path(tempfile.mkdtemp(prefix=f"constraint-route-{case.name}-{round_no:02d}-"))
    patch_path = root / "normalized.patch"
    patch_path.write_text("\n".join(case.patch_lines) + "\n", encoding="utf-8")
    return patch_path


def run_case(case: RouteCase, *, round_no: int) -> dict[str, object]:
    """执行单条路线验证并返回结构化结果"""

    patch_path = make_patch(case, round_no=round_no)
    bundle = PatchBundle(
        task_id=f"constraint-route-{case.name}-{round_no:02d}",
        cve_id="CVE-TEST-0000",
        affected_files=case.affected_files,
        normalized_patch_path=patch_path,
    )
    semantic_card = SemanticCard(
        bug_class="cve_fix",
        root_cause=f"{case.name} 路线验证样例",
        touched_files=case.affected_files,
        touched_functions=[case.semantic_function],
    )

    report = ConstraintDiagnoser().diagnose(
        bundle,
        semantic_card=semantic_card,
        semantic_card_source="deterministic",
        semantic_card_enriched=False,
    )
    plan = JointPlanner().plan(
        task_id=bundle.task_id,
        semantic_card=semantic_card,
        constraint_report=report,
    )

    if report.preferred_route != case.expected_preferred_route:
        raise RuntimeError(
            f"{case.name} 期望 preferred_route={case.expected_preferred_route} 实际为 {report.preferred_route}"
        )
    if case.expected_preferred_route not in report.candidate_routes:
        raise RuntimeError(
            f"{case.name} 缺少候选路线 {case.expected_preferred_route}: {report.candidate_routes}"
        )

    candidate_recipes = [item.recipe_name for item in plan.candidate_summaries]
    if case.expected_candidate_recipe not in candidate_recipes:
        raise RuntimeError(
            f"{case.name} 规划候选里缺少 {case.expected_candidate_recipe}: {candidate_recipes}"
        )
    if plan.selected_recipe != case.expected_selected_recipe:
        raise RuntimeError(
            f"{case.name} 期望 selected_recipe={case.expected_selected_recipe} 实际为 {plan.selected_recipe}"
        )

    return {
        "round": round_no,
        "case": case.name,
        "preferred_route": report.preferred_route,
        "candidate_routes": report.candidate_routes,
        "risk_types": [item.risk_type for item in report.risk_items],
        "suggested_primitives": report.suggested_primitives,
        "route_hints": [item.route_name for item in report.route_hints],
        "selected_recipe": plan.selected_recipe,
        "selected_route_family": plan.selected_route_family,
        "candidate_recipes": candidate_recipes,
    }


def main() -> int:
    """按轮执行约束路线验证"""

    args = parse_args()
    cases = route_cases()
    total = 0
    for round_no in range(1, args.rounds + 1):
        for case in cases:
            total += 1
            payload = run_case(case, round_no=round_no)
            print(json.dumps(payload, ensure_ascii=False))

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
