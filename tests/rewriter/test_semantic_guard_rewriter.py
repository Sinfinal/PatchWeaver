from __future__ import annotations

from patchweaver.models.semantic import RepairIntent
from patchweaver.rewriter.semantic_guard import SemanticGuardRewriter


def _semantic_guard_intent() -> RepairIntent:
    return RepairIntent(
        cve_id="CVE-TEST-0003",
        bug_class="bounds_check",
        guard_conditions=["len > PAGE_SIZE"],
        guard_sites=["demo_parse"],
        safe_exits=["return -EINVAL;"],
        recommended_strategy="semantic_guard",
        confidence=0.8,
    )


def test_semantic_guard_rewriter_keeps_function_local_guard_and_drops_state_hunk() -> None:
    patch_text = "\n".join(
        [
            "diff --git a/fs/demo.c b/fs/demo.c",
            "--- a/fs/demo.c",
            "+++ b/fs/demo.c",
            "@@ -10,6 +10,9 @@ int demo_parse(char *buf, size_t len)",
            "+if (!buf || len > PAGE_SIZE)",
            "+    return -EINVAL;",
            " return 0;",
            "@@ -40,3 +43,4 @@",
            "+static int demo_shadow_state;",
            " int demo_other(void) { return 0; }",
            "",
        ]
    )

    rewritten, report = SemanticGuardRewriter().rewrite(
        patch_text=patch_text,
        repair_intent=_semantic_guard_intent(),
    )

    assert report["status"] == "applied"
    assert report["effective"] is True
    assert report["kept_hunk_count"] == 1
    assert report["dropped_hunk_count"] == 1
    assert "len > PAGE_SIZE" in rewritten
    assert "return -EINVAL" in rewritten
    assert "demo_shadow_state" not in rewritten


def test_semantic_guard_rewriter_passes_through_when_patch_is_already_guard_only() -> None:
    patch_text = "\n".join(
        [
            "diff --git a/fs/demo.c b/fs/demo.c",
            "--- a/fs/demo.c",
            "+++ b/fs/demo.c",
            "@@ -10,6 +10,9 @@ int demo_parse(char *buf, size_t len)",
            "+if (!buf)",
            "+    return -EINVAL;",
            " return 0;",
            "",
        ]
    )

    rewritten, report = SemanticGuardRewriter().rewrite(
        patch_text=patch_text,
        repair_intent=_semantic_guard_intent(),
    )

    assert rewritten == patch_text
    assert report["status"] == "pass_through"
    assert report["effective"] is False


def test_semantic_guard_rewriter_recognizes_guarded_side_effect_hunk() -> None:
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

    rewritten, report = SemanticGuardRewriter().rewrite(
        patch_text=patch_text,
        repair_intent=_semantic_guard_intent(),
    )

    assert rewritten == patch_text
    assert report["status"] == "pass_through"
    assert report["kept_hunk_count"] == 1
    assert "free_anon_bdev" in rewritten


def test_semantic_guard_rewriter_elides_warn_on_guard_call() -> None:
    patch_text = "\n".join(
        [
            "diff --git a/drivers/demo.c b/drivers/demo.c",
            "--- a/drivers/demo.c",
            "+++ b/drivers/demo.c",
            "@@ -10,6 +10,10 @@ static bool demo_rx(struct demo_sta *sta)",
            "+if (WARN_ON_ONCE(!sta->dup_data))",
            "+    return false;",
            " return true;",
            "",
        ]
    )

    rewritten, report = SemanticGuardRewriter().rewrite(
        patch_text=patch_text,
        repair_intent=_semantic_guard_intent(),
    )

    assert report["status"] == "applied"
    assert report["effective"] is True
    assert report["call_elision_count"] == 1
    assert "WARN_ON_ONCE" not in rewritten
    assert "if (unlikely(!sta->dup_data))" in rewritten
    assert "return false" in rewritten


def test_semantic_guard_rewriter_elides_zero_helper_guard() -> None:
    patch_text = "\n".join(
        [
            "diff --git a/fs/btrfs/ioctl.c b/fs/btrfs/ioctl.c",
            "--- a/fs/btrfs/ioctl.c",
            "+++ b/fs/btrfs/ioctl.c",
            "@@ -790,6 +790,9 @@ static int create_snapshot(struct btrfs_root *root)",
            "+if (btrfs_root_refs(&root->root_item) == 0)",
            "+    return -ENOENT;",
            " return 0;",
            "",
        ]
    )

    rewritten, report = SemanticGuardRewriter().rewrite(
        patch_text=patch_text,
        repair_intent=_semantic_guard_intent(),
    )

    assert report["status"] == "applied"
    assert report["effective"] is True
    assert report["call_elision_count"] == 1
    assert "btrfs_root_refs" not in rewritten
    assert "if (!root->root_item.refs)" in rewritten
    assert "return -ENOENT" in rewritten


def test_semantic_guard_rewriter_keeps_warn_when_marked_as_preserved_side_effect() -> None:
    intent = _semantic_guard_intent().model_copy(
        update={"preserved_side_effects": ["WARN_ON_ONCE diagnostic must be preserved"]}
    )
    patch_text = "\n".join(
        [
            "diff --git a/drivers/demo.c b/drivers/demo.c",
            "--- a/drivers/demo.c",
            "+++ b/drivers/demo.c",
            "@@ -10,6 +10,10 @@ static bool demo_rx(struct demo_sta *sta)",
            "+if (WARN_ON_ONCE(!sta->dup_data))",
            "+    return false;",
            " return true;",
            "",
        ]
    )

    rewritten, report = SemanticGuardRewriter().rewrite(patch_text=patch_text, repair_intent=intent)

    assert report["status"] == "pass_through"
    assert report["effective"] is False
    assert report["call_elision_count"] == 0
    assert "WARN_ON_ONCE" in rewritten


def test_semantic_guard_rewriter_skips_non_semantic_guard_intent() -> None:
    intent = _semantic_guard_intent().model_copy(update={"recommended_strategy": "direct_apply"})

    rewritten, report = SemanticGuardRewriter().rewrite(
        patch_text="diff --git a/a.c b/a.c\n",
        repair_intent=intent,
    )

    assert rewritten == "diff --git a/a.c b/a.c\n"
    assert report["status"] == "skipped"


def test_semantic_guard_rewriter_force_allows_planner_selected_guard_route() -> None:
    intent = _semantic_guard_intent().model_copy(update={"recommended_strategy": "direct_apply"})
    patch_text = "\n".join(
        [
            "diff --git a/drivers/demo.c b/drivers/demo.c",
            "--- a/drivers/demo.c",
            "+++ b/drivers/demo.c",
            "@@ -10,6 +10,10 @@ static bool demo_rx(struct demo_sta *sta)",
            "+if (WARN_ON_ONCE(!sta->dup_data))",
            "+    return false;",
            " return true;",
            "",
        ]
    )

    rewritten, report = SemanticGuardRewriter().rewrite(
        patch_text=patch_text,
        repair_intent=intent,
        force=True,
    )

    assert report["status"] == "applied"
    assert report["effective"] is True
    assert "WARN_ON_ONCE" not in rewritten
    assert "unlikely(!sta->dup_data)" in rewritten
