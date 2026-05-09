from __future__ import annotations

import json
from pathlib import Path

import pytest

from patchweaver.models.patch import PatchBundle
from patchweaver.models.rewrite import RewritePlan
from patchweaver.rewriter.executor import RewriteExecutor


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class _BuilderStub:
    """提供最小 builder 探针，避免单测依赖真实源码树"""

    def probe_environment(self) -> dict[str, object]:
        """返回空源码探针，让 apply 预检查走 skip 分支"""

        return {"selected_source_dir": None}


def _write_patch(tmp_path: Path, *, relative_file: str) -> Path:
    """写一份最小 patch 供执行层测试复用"""

    patch_path = tmp_path / "normalized.patch"
    patch_path.write_text(
        "\n".join(
            [
                f"diff --git a/{relative_file} b/{relative_file}",
                f"--- a/{relative_file}",
                f"+++ b/{relative_file}",
                "@@ -1 +1,2 @@",
                "-return old_value;",
                "+return new_value;",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return patch_path


def _make_bundle(tmp_path: Path, *, task_id: str, relative_file: str) -> PatchBundle:
    """构造执行层输入 patch"""

    return PatchBundle(
        task_id=task_id,
        cve_id="CVE-TEST-0000",
        affected_files=[relative_file],
        normalized_patch_path=_write_patch(tmp_path, relative_file=relative_file),
    )


@pytest.mark.parametrize(
    ("recipe_name", "route_family", "execution_mode", "selected_primitives", "relative_file"),
    [
        (
            "callback_livepatch_wrap",
            "callback",
            "callback_scaffold",
            ["wrapper", "callback"],
            "kernel/livepatch/demo.c",
        ),
        (
            "shadow_variable_wrap",
            "shadow_variable",
            "shadow_state_scaffold",
            ["wrapper", "shadow_variable"],
            "kernel/livepatch/demo.c",
        ),
        (
            "callback_shadow_wrap",
            "callback_shadow",
            "callback_shadow_scaffold",
            ["wrapper", "callback", "shadow_variable"],
            "kernel/livepatch/demo.c",
        ),
        (
            "state_preserving_wrap",
            "state_preserving",
            "state_preserving_scaffold",
            ["wrapper", "shadow_variable", "state_preserving"],
            "include/linux/demo.h",
        ),
    ],
)
def test_rewrite_executor_materializes_scaffold_route_artifacts(
    tmp_path: Path,
    recipe_name: str,
    route_family: str,
    execution_mode: str,
    selected_primitives: list[str],
    relative_file: str,
) -> None:
    rewrite_dir = tmp_path / recipe_name
    plan = RewritePlan(
        task_id=f"TASK-{recipe_name}",
        plan_id=f"TASK-{recipe_name}-plan-001",
        selected_recipe=recipe_name,
        selected_route_family=route_family,
        selected_execution_mode=execution_mode,
        selected_primitives=selected_primitives,
        target_files=[relative_file],
        rule_hits=["constraint_review"],
        requires_kernel_scaffold=True,
        scaffold_notes=["需要补齐内核侧辅助逻辑"],
        selection_reason="测试用规划",
    )
    bundle = _make_bundle(tmp_path, task_id=plan.task_id, relative_file=relative_file)

    outputs = RewriteExecutor(PROJECT_ROOT).execute(
        plan=plan,
        patch_bundle=bundle,
        rewrite_dir=rewrite_dir,
        builder=_BuilderStub(),
        task_id=plan.task_id,
        attempt_no=1,
    )

    trace_payload = json.loads(outputs["transformation_trace"].read_text(encoding="utf-8"))
    rewrite_reason = json.loads(outputs["rewrite_reason"].read_text(encoding="utf-8"))
    kernel_adapter_plan = json.loads(outputs["kernel_adapter_plan"].read_text(encoding="utf-8"))
    step_map = {step["engine"]: step for step in trace_payload["steps"]}
    scaffold_files = [PROJECT_ROOT / item for item in kernel_adapter_plan["scaffold_files"]]

    assert outputs["rewritten_patch"].exists()
    assert outputs["apply_precheck_report"].status == "skipped"
    assert rewrite_reason["selected_recipe"] == recipe_name
    assert rewrite_reason["selected_route_family"] == route_family
    assert kernel_adapter_plan["selected_recipe"] == recipe_name
    assert kernel_adapter_plan["selected_execution_mode"] == execution_mode
    assert kernel_adapter_plan["scaffold_contract"]["target_files"] == [relative_file]
    assert scaffold_files
    assert scaffold_files[0].exists()
    scaffold_text = scaffold_files[0].read_text(encoding="utf-8")
    if "callback" in selected_primitives:
        assert "patchweaver_pre_patch_callback" in scaffold_text
    if "shadow_variable" in selected_primitives:
        assert "patchweaver_shadow_state" in scaffold_text
    if "state_preserving" in selected_primitives:
        assert "patchweaver_state_preserve" in scaffold_text
    assert recipe_name in step_map["template"]["summary"]
    assert f"{recipe_name}.cocci" in step_map["smpl"]["summary"]
    assert step_map["route_dispatch"]["action"] == execution_mode
    assert step_map["apply_precheck"]["action"] == "skipped"


def test_rewrite_executor_records_smpl_primary_route_without_kernel_scaffold(tmp_path: Path) -> None:
    rewrite_dir = tmp_path / "smpl-primary"
    plan = RewritePlan(
        task_id="TASK-SMPL-001",
        plan_id="TASK-SMPL-001-plan-001",
        selected_recipe="smpl_primary_rewrite",
        selected_route_family="smpl_primary",
        selected_execution_mode="smpl_primary",
        selected_primitives=["wrapper", "smpl"],
        target_files=["fs/demo.c"],
        rule_hits=["macro_control_flow_change"],
        requires_kernel_scaffold=False,
        selection_reason="测试 SmPL 主导改写",
    )
    bundle = _make_bundle(tmp_path, task_id=plan.task_id, relative_file="fs/demo.c")

    outputs = RewriteExecutor(PROJECT_ROOT).execute(
        plan=plan,
        patch_bundle=bundle,
        rewrite_dir=rewrite_dir,
        builder=_BuilderStub(),
        task_id=plan.task_id,
        attempt_no=1,
    )

    trace_payload = json.loads(outputs["transformation_trace"].read_text(encoding="utf-8"))
    rewrite_reason = json.loads(outputs["rewrite_reason"].read_text(encoding="utf-8"))
    step_map = {step["engine"]: step for step in trace_payload["steps"]}

    assert outputs["rewritten_patch"].exists()
    assert outputs["kernel_adapter_plan"] is None
    assert rewrite_reason["selected_recipe"] == "smpl_primary_rewrite"
    assert rewrite_reason["selected_execution_mode"] == "smpl_primary"
    assert "smpl_primary_rewrite.cocci" in step_map["smpl"]["summary"]
    assert step_map["template"]["summary"].startswith("命中模板")
