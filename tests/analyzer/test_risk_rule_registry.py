from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from patchweaver.analyzer.risk_rule_registry import RiskRuleRegistry
from patchweaver.models.patch import PatchBundle


def _project_root() -> Path:
    current = Path(__file__).resolve().parent
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists():
            return candidate
    raise RuntimeError(f"Unable to locate project root from {__file__}")


def _case_dir(case_name: str) -> Path:
    base_dir = _project_root() / ".pytest_tmp"
    base_dir.mkdir(parents=True, exist_ok=True)
    root = base_dir / f"{case_name}-{uuid4().hex[:8]}"
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_risk_rule_registry_loads_yaml_rules_from_rule_directory() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    tmp_path = _case_dir("risk-rule-load")
    patch_path = tmp_path / "normalized.patch"
    patch_path.write_text(
        "\n".join(
            [
                "diff --git a/include/linux/demo.h b/include/linux/demo.h",
                "--- a/include/linux/demo.h",
                "+++ b/include/linux/demo.h",
                "@@ -1 +1,2 @@",
                "-int old_value;",
                "+static int new_value;",
                "+void ftrace_entry_hook(void);",
                "",
            ]
        ),
        encoding="utf-8",
    )
    bundle = PatchBundle(
        task_id="TASK-RULE-001",
        cve_id="CVE-2099-0005",
        affected_files=["include/linux/demo.h"],
        normalized_patch_path=patch_path,
    )

    items = RiskRuleRegistry(repo_root).evaluate(bundle)
    risk_types = {item.risk_type for item in items}

    assert "direct_apply_ready" in risk_types
    assert "missing_fentry" in risk_types
    assert "global_data_change" in risk_types
    assert "header_abi_change" in risk_types


def test_risk_rule_registry_falls_back_to_unknown_patchability_when_no_rule_hits() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    tmp_path = _case_dir("risk-rule-fallback")
    patch_path = tmp_path / "normalized.patch"
    patch_path.write_text("plain text patch placeholder\n", encoding="utf-8")
    bundle = PatchBundle(
        task_id="TASK-RULE-002",
        cve_id="CVE-2099-0006",
        affected_files=["kernel/demo.c"],
        normalized_patch_path=patch_path,
    )

    items = RiskRuleRegistry(repo_root).evaluate(bundle)

    assert len(items) == 1
    assert items[0].risk_type == "unknown_patchability"
    assert items[0].required_primitives == ["wrapper"]
