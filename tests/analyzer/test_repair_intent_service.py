from __future__ import annotations

from patchweaver.analyzer.repair_intent_service import RepairIntentBuilder
from patchweaver.models.patch import PatchBundle
from patchweaver.models.semantic import SemanticCard


def test_repair_intent_builder_extracts_guard_strategy() -> None:
    patch_text = "\n".join(
        [
            "diff --git a/fs/demo.c b/fs/demo.c",
            "--- a/fs/demo.c",
            "+++ b/fs/demo.c",
            "@@ -10,6 +10,9 @@ int demo_parse(char *buf, size_t len)",
            "+if (!buf || len > PAGE_SIZE)",
            "+    return -EINVAL;",
            " return 0;",
            "",
        ]
    )
    patch_bundle = PatchBundle(
        task_id="TASK-INTENT-001",
        cve_id="CVE-TEST-0001",
        affected_files=["fs/demo.c"],
    )
    semantic_card = SemanticCard(
        bug_class="bounds_check",
        root_cause="缺少长度边界检查",
        touched_files=["fs/demo.c"],
        touched_functions=["demo_parse"],
    )

    repair_intent = RepairIntentBuilder().build(
        patch_bundle=patch_bundle,
        semantic_card=semantic_card,
        patch_text=patch_text,
    )

    assert repair_intent.cve_id == "CVE-TEST-0001"
    assert repair_intent.recommended_strategy == "semantic_guard"
    assert repair_intent.guard_conditions == ["!buf || len > PAGE_SIZE"]
    assert repair_intent.guard_sites == ["demo_parse"]
    assert repair_intent.safe_exits == ["return -EINVAL;"]
    assert repair_intent.touched_files == ["fs/demo.c"]
    assert repair_intent.confidence >= 0.75


def test_repair_intent_builder_routes_state_changes_to_callback_shadow() -> None:
    patch_text = "\n".join(
        [
            "diff --git a/drivers/demo.c b/drivers/demo.c",
            "--- a/drivers/demo.c",
            "+++ b/drivers/demo.c",
            "@@ -1,3 +1,5 @@",
            "+static int demo_shadow_state;",
            "+struct demo_state { int active; };",
            "",
        ]
    )
    patch_bundle = PatchBundle(
        task_id="TASK-INTENT-002",
        cve_id="CVE-TEST-0002",
        affected_files=["drivers/demo.c"],
    )
    semantic_card = SemanticCard(
        bug_class="state_change",
        root_cause="需要补充状态保存",
        touched_files=["drivers/demo.c"],
        touched_functions=["demo_probe"],
    )

    repair_intent = RepairIntentBuilder().build(
        patch_bundle=patch_bundle,
        semantic_card=semantic_card,
        patch_text=patch_text,
    )

    assert repair_intent.recommended_strategy == "callback_shadow"
    assert "static_or_global_data_change" in repair_intent.touched_state
    assert "type_definition_change" in repair_intent.touched_state
    assert repair_intent.confidence < 0.5


def test_repair_intent_builder_keeps_guarded_side_effects_as_semantic_guard() -> None:
    patch_text = "\n".join(
        [
            "diff --git a/fs/btrfs/disk-io.c b/fs/btrfs/disk-io.c",
            "--- a/fs/btrfs/disk-io.c",
            "+++ b/fs/btrfs/disk-io.c",
            "@@ -10,6 +10,10 @@ static struct btrfs_root *btrfs_get_root_ref(void)",
            "+if (unlikely(anon_dev)) {",
            "+    free_anon_bdev(anon_dev);",
            "+    anon_dev = 0;",
            "+}",
            " return root;",
            "",
        ]
    )
    patch_bundle = PatchBundle(
        task_id="TASK-INTENT-003",
        cve_id="CVE-2024-26727",
        affected_files=["fs/btrfs/disk-io.c"],
    )
    semantic_card = SemanticCard(
        bug_class="assertion_fix",
        root_cause="ASSERT 前置假设不成立",
        must_keep_conditions=["btrfs_get_root_ref: unlikely(anon_dev)"],
        touched_files=["fs/btrfs/disk-io.c"],
        touched_functions=["btrfs_get_root_ref"],
    )

    repair_intent = RepairIntentBuilder().build(
        patch_bundle=patch_bundle,
        semantic_card=semantic_card,
        patch_text=patch_text,
    )

    assert repair_intent.recommended_strategy == "semantic_guard"
    assert "free_anon_bdev(anon_dev);" in repair_intent.preserved_side_effects
    assert "anon_dev = 0;" in repair_intent.preserved_side_effects


def test_repair_intent_builder_does_not_promote_condition_without_exit_or_side_effect() -> None:
    patch_text = "\n".join(
        [
            "diff --git a/fs/demo.c b/fs/demo.c",
            "--- a/fs/demo.c",
            "+++ b/fs/demo.c",
            "@@ -10,6 +10,7 @@ int demo_parse(int value)",
            "+if (value > 0)",
            " return value;",
            "",
        ]
    )
    patch_bundle = PatchBundle(
        task_id="TASK-INTENT-004",
        cve_id="CVE-TEST-0004",
        affected_files=["fs/demo.c"],
    )
    semantic_card = SemanticCard(
        bug_class="unknown",
        root_cause="只有条件线索，还不足以驱动 semantic guard",
        touched_files=["fs/demo.c"],
        touched_functions=["demo_parse"],
    )

    repair_intent = RepairIntentBuilder().build(
        patch_bundle=patch_bundle,
        semantic_card=semantic_card,
        patch_text=patch_text,
    )

    assert repair_intent.recommended_strategy == "direct_apply"
