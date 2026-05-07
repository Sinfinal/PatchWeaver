from __future__ import annotations

from patchweaver.harness.livepatchability import (
    analyze_patch_shape,
    apply_livepatchability_gate,
    classify_kpatch_constraint_rewrite,
    score_livepatchability,
)


def test_score_high_for_small_module_guard_patch() -> None:
    patch_text = """diff --git a/drivers/demo/demo.c b/drivers/demo/demo.c
--- a/drivers/demo/demo.c
+++ b/drivers/demo/demo.c
@@ -10,6 +10,8 @@ int demo_ioctl(struct demo *d, size_t len)
 {
+	if (!d || len > 32)
+		return -EINVAL;
 	return 0;
 }
"""
    shape = analyze_patch_shape(patch_text)
    result = score_livepatchability(
        {
            "selected_route": "direct_apply_patch",
            "high_risk_count": 0,
            "patch_shape": shape,
            "inferred_build_targets": ["drivers/demo/demo.ko"],
            "build_target_states": ["module"],
        }
    )

    assert result["tier"] == "high"
    assert result["full_run_recommended"] is True
    assert shape["guard_like"] is True


def test_score_low_for_kbuild_and_struct_change() -> None:
    patch_text = """diff --git a/drivers/demo/Makefile b/drivers/demo/Makefile
--- a/drivers/demo/Makefile
+++ b/drivers/demo/Makefile
@@ -1 +1,2 @@
 obj-m += demo.o
+obj-m += demo-extra.o
diff --git a/include/linux/demo.h b/include/linux/demo.h
--- a/include/linux/demo.h
+++ b/include/linux/demo.h
@@ -1,3 +1,4 @@ struct demo {
 	int a;
+	int new_state;
 };
"""
    result = score_livepatchability(
        {
            "selected_route": "state_preserving_wrap",
            "high_risk_count": 2,
            "patch_shape": analyze_patch_shape(patch_text),
            "inferred_build_targets": ["vmlinux"],
            "build_target_states": ["built_in"],
            "vmlinux_target_candidate": True,
        }
    )

    assert result["tier"] == "low"
    assert result["full_run_recommended"] is False
    assert "修改 Kconfig/Makefile/Kbuild" in result["penalties"]


def test_apply_livepatchability_gate_defers_low_score_positive_candidate() -> None:
    records = [
        {
            "cve_id": "CVE-2024-29999",
            "positive_pool_candidate": True,
            "screening_tier": "positive_candidate_low_risk",
            "patch_shape": {"changed_line_count": 80, "touched_file_count": 3, "risk_markers": ["kbuild_or_makefile_change"]},
            "inferred_build_targets": ["vmlinux"],
            "build_target_states": ["built_in"],
            "vmlinux_target_candidate": True,
        }
    ]

    gated = apply_livepatchability_gate(records, min_score=75, only_high=True)

    assert gated[0]["positive_pool_candidate"] is False
    assert gated[0]["screening_tier"] == "deferred_livepatchability_low_score"
    assert gated[0]["livepatchability_tier"] == "low"


def test_apply_livepatchability_gate_caps_known_kpatch_pool_case() -> None:
    records = [
        {
            "cve_id": "CVE-2024-26643",
            "known_pool_hit": "kpatch_constraint_pool",
            "positive_pool_candidate": False,
            "patch_shape": {"changed_line_count": 8, "touched_file_count": 1, "touched_function_count": 1},
            "inferred_build_targets": ["drivers/demo/demo.ko"],
            "build_target_states": ["module"],
        }
    ]

    gated = apply_livepatchability_gate(records, min_score=75, only_high=True)

    assert gated[0]["livepatchability_tier"] == "low"
    assert gated[0]["livepatchability_score"] <= 40


def test_classify_kpatch_constraint_guard_rewrite_candidate() -> None:
    classification = classify_kpatch_constraint_rewrite(
        {
            "patch_shape": {
                "guard_like": True,
                "changed_line_count": 8,
                "touched_function_count": 1,
                "risk_markers": [],
            }
        }
    )

    assert classification["class"] == "rewritable_by_semantic_guard"
    assert classification["next_strategy"] == "semantic_guard_rewrite"
