from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from patchweaver.models.attempt import AttemptRecord, BuildSummary
from patchweaver.models.constraint import ConstraintReport
from patchweaver.models.patch import PatchBundle
from patchweaver.models.semantic import SemanticCard
from patchweaver.models.task import TaskContext
from patchweaver.models.validation import ValidationItem
from patchweaver.planner.joint_planner import JointPlanner
from patchweaver.rewriter.executor import RewriteExecutor
from patchweaver.validator.validator import Validator


class BuilderStub:
    """提供最小 builder 探针，避免单测依赖真实源码树"""

    def probe_environment(self) -> dict[str, object]:
        """返回空源码目录，让 apply 预检查按预期 skip"""

        return {"selected_source_dir": None}


class LoadTesterStub:
    """模拟模块加载和卸载成功"""

    def load(self, *, module_path: Path | None):
        """返回加载成功结果"""

        return ValidationItem(status="passed", ok=True, detail=f"加载 {module_path.name} 成功"), "load ok\n"

    def unload(self, *, module_path: Path | None):
        """返回卸载成功结果"""

        return ValidationItem(status="passed", ok=True, detail=f"卸载 {module_path.name} 成功"), "unload ok\n"


class SmokeTesterStub:
    """模拟冒烟测试成功"""

    def run(self):
        """返回冒烟成功结果"""

        return ValidationItem(status="passed", ok=True, detail="冒烟测试通过"), "smoke ok\n"


class RegressionTesterStub:
    """模拟回归测试成功"""

    def run(self, *, current_attempt, history_attempts, semantic_guard_passed):
        """返回回归成功结果"""

        return (
            ValidationItem(status="passed", ok=True, detail="回归验证通过"),
            {
                "current_attempt": current_attempt.attempt_id,
                "history_attempts": len(history_attempts),
                "semantic_guard_passed": semantic_guard_passed,
            },
            "regression ok\n",
        )


class SelftestRunnerStub:
    """模拟构建产物自检成功"""

    def run(self, *, build_succeeded: bool, module_path: Path | None, risk_level: str):
        """返回自检成功结果"""

        return ValidationItem(status="passed", ok=True, detail=f"自检通过，风险等级 {risk_level}"), "selftest ok\n"


@dataclass(frozen=True)
class ComplexRouteCase:
    """描述一条复杂改写路线的单元验证样例"""

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
    expected_recipe: str
    expected_family: str
    expected_execution_mode: str
    expect_kernel_adapter: bool


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""

    parser = argparse.ArgumentParser(description="6.5 复杂路线动态验证闭环烟测")
    parser.add_argument("--rounds", type=int, default=5, help="连续验证轮数")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "data" / "logs" / "complex_route_validation_smoke.json",
        help="汇总结果输出路径",
    )
    return parser.parse_args()


def route_cases() -> list[ComplexRouteCase]:
    """返回需要覆盖的复杂路线集合"""

    return [
        ComplexRouteCase(
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
            expected_recipe="callback_livepatch_wrap",
            expected_family="callback",
            expected_execution_mode="callback_scaffold",
            expect_kernel_adapter=True,
        ),
        ComplexRouteCase(
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
            expected_recipe="shadow_variable_wrap",
            expected_family="shadow_variable",
            expected_execution_mode="shadow_state_scaffold",
            expect_kernel_adapter=True,
        ),
        ComplexRouteCase(
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
            expected_recipe="callback_shadow_wrap",
            expected_family="callback_shadow",
            expected_execution_mode="callback_shadow_scaffold",
            expect_kernel_adapter=True,
        ),
        ComplexRouteCase(
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
            expected_recipe="state_preserving_wrap",
            expected_family="state_preserving",
            expected_execution_mode="state_preserving_scaffold",
            expect_kernel_adapter=True,
        ),
        ComplexRouteCase(
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
            expected_recipe="smpl_primary_rewrite",
            expected_family="smpl_primary",
            expected_execution_mode="smpl_primary",
            expect_kernel_adapter=False,
        ),
    ]


def make_patch(case: ComplexRouteCase, *, case_dir: Path) -> Path:
    """生成最小 unified diff 输入"""

    patch_path = case_dir / "normalized.patch"
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


def make_constraint(case: ComplexRouteCase, *, task_id: str) -> ConstraintReport:
    """构造复杂路线约束报告"""

    return ConstraintReport(
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
        summary=f"{case.name} 路线动态验证闭环样例",
    )


def make_plan(case: ComplexRouteCase, *, task_id: str, constraint_report: ConstraintReport):
    """生成改写规划"""

    semantic_card = SemanticCard(
        bug_class="cve_fix",
        root_cause=f"{case.name} 路线验证样例",
        touched_files=[case.relative_file],
        touched_functions=[case.semantic_function],
    )
    return JointPlanner().plan(
        task_id=task_id,
        semantic_card=semantic_card,
        constraint_report=constraint_report,
    )


def make_validator() -> Validator:
    """构造严格档位验证器"""

    verify_config = SimpleNamespace(
        verification_profile="strict",
        enable_semantic_guard=True,
        enable_load_test=True,
        enable_unload_test=True,
        enable_smoke_test=True,
        enable_regression=True,
        smoke_test_script="scripts/validate_smoke.sh",
    )
    return Validator(
        verify_config=verify_config,
        build_config=SimpleNamespace(build_backend="local"),
        project_root=PROJECT_ROOT,
        load_tester=LoadTesterStub(),
        smoke_tester=SmokeTesterStub(),
        regression_tester=RegressionTesterStub(),
        selftest_runner=SelftestRunnerStub(),
    )


def run_case(case: ComplexRouteCase, *, round_no: int, workspace_root: Path) -> dict[str, object]:
    """执行单条复杂路线闭环验证"""

    task_id = f"complex-route-{case.name}-{round_no:02d}"
    case_dir = workspace_root / task_id
    rewrite_dir = case_dir / "rewrite"
    attempt_dir = case_dir / "attempts" / "001"
    artifacts_dir = attempt_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    constraint_report = make_constraint(case, task_id=task_id)
    plan = make_plan(case, task_id=task_id, constraint_report=constraint_report)
    patch_path = make_patch(case, case_dir=case_dir)
    bundle = PatchBundle(
        task_id=task_id,
        cve_id="CVE-UNIT-0000",
        affected_files=[case.relative_file],
        normalized_patch_path=patch_path,
    )

    rewrite_outputs = RewriteExecutor(PROJECT_ROOT).execute(
        plan=plan,
        patch_bundle=bundle,
        rewrite_dir=rewrite_dir,
        builder=BuilderStub(),
        task_id=task_id,
        attempt_no=1,
    )

    module_path = artifacts_dir / f"{task_id}.ko"
    module_path.write_text("fake ko for complex route validation\n", encoding="utf-8")
    attempt = AttemptRecord(
        task_id=task_id,
        attempt_no=1,
        attempt_id=f"{task_id}-A001",
        status="built",
        module_path=module_path,
        rewritten_patch_path=rewrite_outputs["rewritten_patch"],
    )
    build_summary = BuildSummary(
        task_id=task_id,
        attempt_id=attempt.attempt_id,
        backend="local",
        builder_cmd="kpatch-build",
        status="built",
        summary="complex route unit build artifact",
        rewritten_patch_path=rewrite_outputs["rewritten_patch"],
        module_path=module_path,
        build_exec_status="executed",
    )
    task = TaskContext(
        task_id=task_id,
        cve_id="CVE-UNIT-0000",
        target_kernel="6.6.102-5.2.an23.x86_64",
        workspace_dir=case_dir,
    )
    report, artifacts = make_validator().run(
        task=task,
        attempt=attempt,
        attempt_dir=attempt_dir,
        rewritten_patch_path=rewrite_outputs["rewritten_patch"],
        build_summary=build_summary,
        constraint_report=constraint_report,
        history_attempts=[],
    )

    kernel_adapter_path = rewrite_outputs.get("kernel_adapter_plan")
    has_kernel_adapter = kernel_adapter_path is not None and Path(kernel_adapter_path).exists()
    kernel_adapter_scaffold_path: Path | None = None
    has_kernel_adapter_scaffold = False
    if has_kernel_adapter:
        kernel_adapter_payload = json.loads(Path(kernel_adapter_path).read_text(encoding="utf-8"))
        scaffold_files = kernel_adapter_payload.get("scaffold_files") or []
        for scaffold_file in scaffold_files:
            candidate_path = PROJECT_ROOT / scaffold_file
            if candidate_path.name == "kernel_adapter_scaffold.c" and candidate_path.exists():
                kernel_adapter_scaffold_path = candidate_path
                has_kernel_adapter_scaffold = True
                break
    candidate_recipes = [item.recipe_name for item in plan.candidate_summaries]

    if plan.selected_recipe != case.expected_recipe:
        raise RuntimeError(f"{case.name} selected_recipe 异常: {plan.selected_recipe}")
    if plan.selected_route_family != case.expected_family:
        raise RuntimeError(f"{case.name} route_family 异常: {plan.selected_route_family}")
    if plan.selected_execution_mode != case.expected_execution_mode:
        raise RuntimeError(f"{case.name} execution_mode 异常: {plan.selected_execution_mode}")
    if has_kernel_adapter != case.expect_kernel_adapter:
        raise RuntimeError(f"{case.name} kernel_adapter_plan 异常: {has_kernel_adapter}")
    if has_kernel_adapter_scaffold != case.expect_kernel_adapter:
        raise RuntimeError(f"{case.name} kernel_adapter_scaffold 异常: {has_kernel_adapter_scaffold}")
    if report.status != "passed":
        raise RuntimeError(f"{case.name} validation 未通过: {report.status}")
    if not report.load_result.ok or not report.unload_result.ok or not report.smoke_result.ok:
        raise RuntimeError(f"{case.name} 动态验证未完整通过")
    if report.semantic_guard_result.status != "passed":
        raise RuntimeError(f"{case.name} semantic_guard 未通过: {report.semantic_guard_result.status}")
    if report.regression_result.status != "passed":
        raise RuntimeError(f"{case.name} regression 未通过: {report.regression_result.status}")

    return {
        "round": round_no,
        "case": case.name,
        "task_id": task_id,
        "selected_recipe": plan.selected_recipe,
        "selected_route_family": plan.selected_route_family,
        "selected_execution_mode": plan.selected_execution_mode,
        "candidate_recipes": candidate_recipes,
        "kernel_adapter_plan": has_kernel_adapter,
        "kernel_adapter_scaffold": has_kernel_adapter_scaffold,
        "kernel_adapter_scaffold_path": str(kernel_adapter_scaffold_path) if kernel_adapter_scaffold_path else None,
        "module_path": str(module_path),
        "validation_status": report.status,
        "load_status": report.load_result.status,
        "unload_status": report.unload_result.status,
        "smoke_status": report.smoke_result.status,
        "semantic_guard_status": report.semantic_guard_result.status,
        "regression_status": report.regression_result.status,
        "validation_report_path": str(artifacts["validation_report"]),
    }


def main() -> int:
    """连续执行复杂路线动态验证闭环烟测"""

    args = parse_args()
    cases = route_cases()
    workspace_root = Path(tempfile.mkdtemp(prefix="patchweaver-complex-route-validation-"))
    results: list[dict[str, object]] = []

    for round_no in range(1, args.rounds + 1):
        for case in cases:
            result = run_case(case, round_no=round_no, workspace_root=workspace_root)
            results.append(result)
            print(json.dumps(result, ensure_ascii=False))

    summary = {
        "status": "passed",
        "rounds": args.rounds,
        "cases": [case.name for case in cases],
        "total_runs": len(results),
        "workspace_root": str(workspace_root),
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ["status", "rounds", "cases", "total_runs", "workspace_root"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
