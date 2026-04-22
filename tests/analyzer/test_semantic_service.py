from __future__ import annotations

from pathlib import Path

from patchweaver.analyzer.semantic_service import SemanticAnalyzer
from patchweaver.models.patch import PatchBundle, SourceEvidence
from patchweaver.models.task import TaskContext


def _build_task(tmp_path: Path, cve_id: str) -> TaskContext:
    return TaskContext(
        task_id=f"{cve_id.lower()}-task",
        cve_id=cve_id,
        target_kernel="6.6.102-5.2.an23.x86_64",
        workspace_dir=tmp_path,
    )


def test_semantic_analyzer_extracts_function_conditions_and_root_cause(tmp_path: Path) -> None:
    patch_path = tmp_path / "raw.patch"
    patch_path.write_text(
        """From 722d94847de29310e8aa03fcbdb41fc92c521756 Mon Sep 17 00:00:00 2001
From: Jamie Hill-Daniel <jamie@hill-daniel.co.uk>
Subject: vfs: fs_context: fix up param length parsing in legacy_parse_param

The "PAGE_SIZE - 2 - size" calculation in legacy_parse_param() is an
unsigned type so a large value of "size" results in a high positive
value instead of a negative value as expected. Fix this by getting rid
of the subtraction.

---
diff --git a/fs/fs_context.c b/fs/fs_context.c
index b7e43a780a625..24ce12f0db32e 100644
--- a/fs/fs_context.c
+++ b/fs/fs_context.c
@@ -548,7 +548,7 @@ static int legacy_parse_param(struct fs_context *fc, struct fs_parameter *param)
 			      param->key);
 	}
 
-	if (len > PAGE_SIZE - 2 - size)
+	if (size + len + 2 > PAGE_SIZE)
 		return invalf(fc, "VFS: Legacy: Cumulative options too large");
 	if (strchr(param->key, ',') ||
 	    (param->type == fs_value_is_string &&
""",
        encoding="utf-8",
    )
    bundle = PatchBundle(
        task_id="cve-2022-0185-task",
        cve_id="CVE-2022-0185",
        commit_message="vfs: fs_context: fix up param length parsing in legacy_parse_param",
        affected_files=["fs/fs_context.c"],
        raw_patch_path=patch_path,
        source_evidence=[
            SourceEvidence(
                source_name="nvd",
                url="https://example.invalid/nvd",
                summary=(
                    "A heap-based buffer overflow flaw was found in the way the "
                    "legacy_parse_param function verified the supplied parameters length."
                ),
                stage="metadata",
            )
        ],
    )

    card = SemanticAnalyzer().analyze(_build_task(tmp_path, "CVE-2022-0185"), bundle)

    assert card.touched_files == ["fs/fs_context.c"]
    assert card.touched_functions == ["legacy_parse_param"]
    assert card.must_keep_conditions == ["legacy_parse_param: size + len + 2 > PAGE_SIZE"]
    assert "invalf" in card.critical_calls
    assert "strchr" in card.critical_calls
    assert any("条件 size + len + 2 > PAGE_SIZE 命中时返回 invalf(...)" in item for item in card.must_keep_side_effects)
    assert "legacy_parse_param 中存在" in card.root_cause
    assert "len > PAGE_SIZE - 2 - size" in card.root_cause
    assert "size + len + 2 > PAGE_SIZE" in card.root_cause


def test_semantic_analyzer_merges_multiline_conditions(tmp_path: Path) -> None:
    patch_path = tmp_path / "raw.patch"
    patch_path.write_text(
        """Subject: demo: tighten foo guard

---
diff --git a/kernel/demo.c b/kernel/demo.c
--- a/kernel/demo.c
+++ b/kernel/demo.c
@@ -10,8 +10,8 @@ static int demo_check(struct demo_ctx *ctx, int len)
-	if (ctx->ready &&
-	    len > ctx->limit)
+	if (ctx->ready &&
+	    len + ctx->used > ctx->limit)
 		return warn_once(ctx);
 	return 0;
""",
        encoding="utf-8",
    )
    bundle = PatchBundle(
        task_id="demo-task",
        cve_id="CVE-2099-0001",
        commit_message="demo: tighten foo guard",
        affected_files=["kernel/demo.c"],
        raw_patch_path=patch_path,
    )

    card = SemanticAnalyzer().analyze(_build_task(tmp_path, "CVE-2099-0001"), bundle)

    assert card.touched_files == ["kernel/demo.c"]
    assert card.touched_functions == ["demo_check"]
    assert card.must_keep_conditions == ["demo_check: ctx->ready && len + ctx->used > ctx->limit"]
    assert "warn_once" in card.critical_calls
    assert any("warn_once" in item for item in card.must_keep_side_effects)


def test_semantic_analyzer_fallback_keeps_file_scope_without_fake_functions(tmp_path: Path) -> None:
    bundle = PatchBundle(
        task_id="fallback-task",
        cve_id="CVE-2099-0002",
        commit_message="demo: fallback summary",
        affected_files=["kernel/fallback.c"],
        raw_patch_path=tmp_path / "missing.patch",
        source_evidence=[
            SourceEvidence(
                source_name="nvd",
                url="https://example.invalid/fallback",
                summary="Fallback path still needs a stable summary for downstream stages",
                stage="metadata",
            )
        ],
    )

    card = SemanticAnalyzer().analyze(_build_task(tmp_path, "CVE-2099-0002"), bundle)

    assert card.touched_files == ["kernel/fallback.c"]
    assert card.touched_functions == []
    assert card.root_cause == "Fallback path still needs a stable summary for downstream stages"


def test_semantic_analyzer_keeps_function_scope_empty_when_header_has_no_function(tmp_path: Path) -> None:
    patch_path = tmp_path / "raw.patch"
    patch_path.write_text(
        """Subject: demo: patch without function header

---
diff --git a/kernel/demo.c b/kernel/demo.c
--- a/kernel/demo.c
+++ b/kernel/demo.c
@@ -10,3 +10,3 @@
-	if (foo > limit)
+	if (foo >= limit)
 		return -EINVAL;
""",
        encoding="utf-8",
    )
    bundle = PatchBundle(
        task_id="no-func-header-task",
        cve_id="CVE-2099-0003",
        commit_message="demo: patch without function header",
        affected_files=["kernel/demo.c"],
        raw_patch_path=patch_path,
    )

    card = SemanticAnalyzer().analyze(_build_task(tmp_path, "CVE-2099-0003"), bundle)

    assert card.touched_files == ["kernel/demo.c"]
    assert card.touched_functions == []
    assert card.must_keep_conditions == ["foo >= limit"]
    assert card.must_keep_side_effects == ["条件 foo >= limit 命中时返回 -EINVAL"]
