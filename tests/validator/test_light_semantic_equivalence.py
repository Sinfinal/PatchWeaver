from __future__ import annotations

import json
from pathlib import Path

from patchweaver.validator.semantic_equivalence import run_light_semantic_equivalence


def test_light_semantic_equivalence_writes_passed_contract(tmp_path: Path) -> None:
    repair_intent = tmp_path / "repair_intent.json"
    semantic_guard = tmp_path / "semantic_guard.json"
    rewritten_patch = tmp_path / "rewritten.patch"
    output_path = tmp_path / "semantic_equivalence.json"

    repair_intent.write_text(
        json.dumps(
            {
                "cve_id": "CVE-2099-1001",
                "guard_conditions": ["len > MAX_SIZE"],
                "safe_exits": ["return -EINVAL"],
                "preserved_side_effects": ["audit_log"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    semantic_guard.write_text(
        json.dumps(
            {
                "status": "passed",
                "guard_conditions": ["len > MAX_SIZE"],
                "safe_exits": ["return -EINVAL"],
                "preserved_side_effects": ["audit_log"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    rewritten_patch.write_text(
        "\n".join(
            [
                "diff --git a/kernel/demo.c b/kernel/demo.c",
                "--- a/kernel/demo.c",
                "+++ b/kernel/demo.c",
                "@@ -10,6 +10,10 @@ int demo(int len)",
                "+if (len > MAX_SIZE) {",
                "+    audit_log(\"oversized\");",
                "+    return -EINVAL;",
                "+}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_light_semantic_equivalence(
        repair_intent_path=repair_intent,
        semantic_guard_path=semantic_guard,
        rewritten_patch_path=rewritten_patch,
        output_path=output_path,
    )

    assert result["status"] == "passed"
    assert result["mode"] == "light_semantic"
    assert result["summary"]["missing_required_items"] == 0
    assert output_path.exists()
    assert json.loads(output_path.read_text(encoding="utf-8"))["cve_id"] == "CVE-2099-1001"


def test_light_semantic_equivalence_reports_missing_safe_exit(tmp_path: Path) -> None:
    repair_intent = tmp_path / "repair_intent.json"
    semantic_guard = tmp_path / "semantic_guard.json"
    rewritten_patch = tmp_path / "rewritten.patch"

    repair_intent.write_text(
        json.dumps({"cve_id": "CVE-2099-1002", "safe_exits": ["return -EINVAL"]}),
        encoding="utf-8",
    )
    semantic_guard.write_text(json.dumps({"status": "passed"}), encoding="utf-8")
    rewritten_patch.write_text(
        "diff --git a/a.c b/a.c\n--- a/a.c\n+++ b/a.c\n@@ -1 +1 @@\n+return 0;\n",
        encoding="utf-8",
    )

    result = run_light_semantic_equivalence(
        repair_intent_path=repair_intent,
        semantic_guard_path=semantic_guard,
        rewritten_patch_path=rewritten_patch,
        output_path=tmp_path / "semantic_equivalence.json",
    )

    assert result["status"] == "failed"
    assert result["checks"]["safe_exits"]["missing"] == ["return -EINVAL"]
