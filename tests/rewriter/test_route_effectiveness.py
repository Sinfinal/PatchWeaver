from __future__ import annotations

import json
from pathlib import Path

from patchweaver.models.rewrite import RewritePlan
from patchweaver.rewriter.effectiveness import build_route_effectiveness_report


def _plan(recipe: str) -> RewritePlan:
    return RewritePlan(
        task_id="TASK-ROUTE-EFFECT",
        plan_id=f"TASK-ROUTE-EFFECT-{recipe}",
        selected_recipe=recipe,
    )


def test_route_effectiveness_marks_identical_patch_as_ineffective(tmp_path: Path) -> None:
    previous = tmp_path / "attempts" / "001"
    current = tmp_path / "attempts" / "002"
    previous_rewrite = previous / "rewrite"
    current_rewrite = current / "rewrite"
    previous_rewrite.mkdir(parents=True)
    current_rewrite.mkdir(parents=True)
    patch_text = "\n".join(
        [
            "diff --git a/a.c b/a.c",
            "--- a/a.c",
            "+++ b/a.c",
            "@@ -1 +1 @@ int f(void)",
            "-return -1;",
            "+return 0;",
        ]
    ) + "\n"
    (previous_rewrite / "rewritten.patch").write_text(patch_text, encoding="utf-8")
    (current_rewrite / "rewritten.patch").write_text(patch_text, encoding="utf-8")
    (previous_rewrite / "rewrite_plan.json").write_text(
        json.dumps(_plan("direct_apply_patch").model_dump(mode="json")),
        encoding="utf-8",
    )

    report = build_route_effectiveness_report(
        project_root=tmp_path,
        task_id="TASK-ROUTE-EFFECT",
        attempt_no=2,
        current_plan=_plan("section_change_avoidance_rewrite"),
        current_patch_path=current_rewrite / "rewritten.patch",
        previous_attempt_dir=previous,
    )

    assert report["status"] == "ineffective_retry"
    assert report["previous_recipe"] == "direct_apply_patch"
    assert report["current_recipe"] == "section_change_avoidance_rewrite"


def test_route_effectiveness_marks_changed_patch_as_effective(tmp_path: Path) -> None:
    previous = tmp_path / "attempts" / "001"
    current = tmp_path / "attempts" / "002"
    previous_rewrite = previous / "rewrite"
    current_rewrite = current / "rewrite"
    previous_rewrite.mkdir(parents=True)
    current_rewrite.mkdir(parents=True)
    (previous_rewrite / "rewritten.patch").write_text("-return -1;\n+return 0;\n", encoding="utf-8")
    (current_rewrite / "rewritten.patch").write_text("-return -2;\n+return 1;\n", encoding="utf-8")
    (previous_rewrite / "rewrite_plan.json").write_text(
        json.dumps(_plan("direct_apply_patch").model_dump(mode="json")),
        encoding="utf-8",
    )

    report = build_route_effectiveness_report(
        project_root=tmp_path,
        task_id="TASK-ROUTE-EFFECT",
        attempt_no=2,
        current_plan=_plan("section_change_avoidance_rewrite"),
        current_patch_path=current_rewrite / "rewritten.patch",
        previous_attempt_dir=previous,
    )

    assert report["status"] == "effective_retry"
