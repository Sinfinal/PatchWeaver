from __future__ import annotations

from pathlib import Path
import tempfile
from uuid import uuid4

from patchweaver.analyzer.constraint_service import ConstraintDiagnoser
from patchweaver.models.patch import PatchBundle
from patchweaver.models.semantic import SemanticCard


def _case_dir(case_name: str) -> Path:
    base_dir = Path(tempfile.gettempdir()) / "patchweaver-pytest"
    base_dir.mkdir(parents=True, exist_ok=True)
    root = base_dir / f"{case_name}-{uuid4().hex[:8]}"
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_constraint_diagnoser_builds_route_hints_for_direct_apply_path() -> None:
    tmp_path = _case_dir("constraint-service-direct-apply")
    patch_path = tmp_path / "normalized.patch"
    patch_path.write_text(
        "\n".join(
            [
                "diff --git a/fs/demo.c b/fs/demo.c",
                "--- a/fs/demo.c",
                "+++ b/fs/demo.c",
                "@@ -1 +1 @@",
                "-if (old_guard)",
                "+if (size + len > limit)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    bundle = PatchBundle(
        task_id="TASK-CONSTRAINT-001",
        cve_id="CVE-2099-0008",
        affected_files=["fs/demo.c"],
        normalized_patch_path=patch_path,
    )
    semantic_card = SemanticCard(
        bug_class="cve_fix",
        root_cause="条件收紧",
        touched_files=["fs/demo.c"],
        touched_functions=["demo_check"],
        must_keep_conditions=["demo_check: size + len > limit"],
    )

    report = ConstraintDiagnoser().diagnose(
        bundle,
        semantic_card=semantic_card,
        semantic_card_source="deterministic",
        semantic_card_enriched=False,
    )

    assert report.risk_items == []
    assert report.direct_apply_viable is True
    assert report.suggested_primitives == ["direct_apply"]
    assert report.route_hints[0].route_name == "direct_apply_patch"
    assert report.semantic_card_source == "deterministic"
    assert report.semantic_card_enriched is False
    assert report.candidate_routes == ["direct_apply_patch"]
    assert report.preferred_route == "direct_apply_patch"
    assert report.target_functions == ["demo_check"]


def test_constraint_diagnoser_uses_semantic_card_to_enrich_risk_items() -> None:
    tmp_path = _case_dir("constraint-service-risk")
    patch_path = tmp_path / "normalized.patch"
    patch_path.write_text(
        "\n".join(
            [
                "diff --git a/include/linux/demo.h b/include/linux/demo.h",
                "--- a/include/linux/demo.h",
                "+++ b/include/linux/demo.h",
                "@@ -1 +1,3 @@",
                "+static int local_state = 0;",
                "+void ftrace_entry_hook(void);",
                "+static inline int demo_inline(void) { return local_state; }",
                "",
            ]
        ),
        encoding="utf-8",
    )
    bundle = PatchBundle(
        task_id="TASK-CONSTRAINT-002",
        cve_id="CVE-2099-0009",
        affected_files=["include/linux/demo.h"],
        normalized_patch_path=patch_path,
    )
    semantic_card = SemanticCard(
        bug_class="cve_fix",
        root_cause="内联路径和状态对象变更",
        touched_files=["include/linux/demo.h"],
        touched_functions=["demo_inline"],
        must_keep_conditions=["demo_inline: local_state >= 0"],
        critical_calls=["ftrace_entry_hook"],
    )

    report = ConstraintDiagnoser().diagnose(
        bundle,
        semantic_card=semantic_card,
        semantic_card_source="enriched",
        semantic_card_enriched=True,
    )
    risk_types = {item.risk_type for item in report.risk_items}

    assert "no_fentry_target" in risk_types
    assert "header_abi_change" in risk_types
    assert "inline_side_effect" in risk_types
    assert report.requires_callback is True
    assert report.requires_shadow_variable is True
    assert "shadow_variable" in report.suggested_primitives
    assert report.route_hints[0].route_name == "minimal_livepatch_wrap"
    assert report.semantic_card_source == "enriched"
    assert report.semantic_card_enriched is True
    assert report.preferred_route == "callback_shadow_wrap"
    assert report.candidate_routes[:2] == ["callback_shadow_wrap", "state_preserving_wrap"]
    assert all(item.affected_functions == ["demo_inline"] for item in report.risk_items)
