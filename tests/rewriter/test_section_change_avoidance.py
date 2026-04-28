from __future__ import annotations

from patchweaver.rewriter.section_change import SectionChangeAvoidance


def test_section_change_avoidance_drops_global_hunk_and_keeps_function_hunk() -> None:
    patch_text = "\n".join(
        [
            "diff --git a/drivers/demo/demo.c b/drivers/demo/demo.c",
            "--- a/drivers/demo/demo.c",
            "+++ b/drivers/demo/demo.c",
            "@@ -1,4 +1,5 @@ static const struct demo_ops demo_ops = {",
            "+\t.probe = demo_probe,",
            " };",
            "@@ -20,7 +21,7 @@ static int demo_open(struct inode *inode)",
            "-\treturn -EINVAL;",
            "+\treturn 0;",
        ]
    ) + "\n"

    rewritten, report = SectionChangeAvoidance().rewrite(patch_text)

    assert report["effective"] is True
    assert report["dropped_hunk_count"] == 1
    assert "demo_open" in rewritten
    assert ".probe = demo_probe" not in rewritten
    assert "return 0;" in rewritten


def test_section_change_avoidance_keeps_original_when_no_safe_hunk_exists() -> None:
    patch_text = "\n".join(
        [
            "diff --git a/drivers/demo/demo.c b/drivers/demo/demo.c",
            "--- a/drivers/demo/demo.c",
            "+++ b/drivers/demo/demo.c",
            "@@ -1,4 +1,5 @@ static const struct demo_ops demo_ops = {",
            "+\t.probe = demo_probe,",
            " };",
        ]
    ) + "\n"

    rewritten, report = SectionChangeAvoidance().rewrite(patch_text)

    assert report["effective"] is False
    assert rewritten == patch_text


def test_section_change_avoidance_preserves_dependency_hunk() -> None:
    patch_text = "\n".join(
        [
            "diff --git a/net/demo/demo.c b/net/demo/demo.c",
            "--- a/net/demo/demo.c",
            "+++ b/net/demo/demo.c",
            "@@ -1,4 +1,5 @@ static const struct nla_policy demo_policy[] = {",
            "+static u32 rate_with_burst;",
            " };",
            "@@ -20,7 +21,8 @@ static int demo_eval(struct demo_ctx *ctx)",
            "-\treturn demo_limit(ctx);",
            "+\tif (rate_with_burst)",
            "+\t\treturn demo_limit(ctx);",
        ]
    ) + "\n"

    rewritten, report = SectionChangeAvoidance().rewrite(patch_text)

    assert report["effective"] is False
    assert report["dependency_gap"] is False
    assert report["kept_dependencies"] == ["rate_with_burst"]
    assert "rate_with_burst" in rewritten
    assert "demo_eval" in rewritten


def test_section_change_avoidance_reports_no_dependency_gap_after_preserve() -> None:
    patch_text = "\n".join(
        [
            "diff --git a/net/demo/demo.c b/net/demo/demo.c",
            "--- a/net/demo/demo.c",
            "+++ b/net/demo/demo.c",
            "@@ -1,4 +1,5 @@ static const struct nla_policy demo_policy[] = {",
            "+static int demo_helper;",
            " };",
            "@@ -20,7 +21,8 @@ static int demo_eval(struct demo_ctx *ctx)",
            "-\treturn -EINVAL;",
            "+\treturn demo_helper;",
        ]
    ) + "\n"

    _, report = SectionChangeAvoidance().rewrite(patch_text)

    assert report["unresolved_dependencies"] == []
    assert report["dependency_gap"] is False
