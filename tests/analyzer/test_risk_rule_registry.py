from __future__ import annotations

from pathlib import Path
import tempfile
from uuid import uuid4

from patchweaver.analyzer.risk_rule_registry import RiskRuleRegistry
from patchweaver.models.patch import PatchBundle
from patchweaver.models.semantic import SemanticCard


def _project_root() -> Path:
    current = Path(__file__).resolve().parent
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists():
            return candidate
    raise RuntimeError(f"Unable to locate project root from {__file__}")


def _case_dir(case_name: str) -> Path:
    base_dir = Path(tempfile.gettempdir()) / "patchweaver-pytest"
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

    semantic_card = SemanticCard(
        bug_class="cve_fix",
        root_cause="头文件与全局对象改动",
        touched_files=["include/linux/demo.h"],
        touched_functions=["demo_entry"],
        must_keep_conditions=["demo_entry: flag && ready"],
        critical_calls=["ftrace_entry_hook"],
    )

    items = RiskRuleRegistry(repo_root).evaluate(bundle, semantic_card=semantic_card)
    risk_types = {item.risk_type for item in items}

    assert "no_fentry_target" in risk_types
    assert "static_local_change" in risk_types
    assert "global_data_change" in risk_types
    assert "header_abi_change" in risk_types
    assert "direct_apply_ready" not in risk_types
    assert all(item.affected_functions == ["demo_entry"] for item in items)
    assert any("关键条件: demo_entry: flag && ready" in entry for item in items for entry in item.evidence)
    assert any("命中语句:" in entry for item in items for entry in item.evidence)


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

    semantic_card = SemanticCard(
        bug_class="cve_fix",
        root_cause="普通路径调整",
        touched_files=["kernel/demo.c"],
        touched_functions=["demo_check"],
    )

    items = RiskRuleRegistry(repo_root).evaluate(bundle, semantic_card=semantic_card)

    assert len(items) == 1
    assert items[0].risk_type == "unknown_patchability"
    assert items[0].required_primitives == ["wrapper"]
    assert items[0].affected_functions == ["demo_check"]


def test_risk_rule_registry_returns_no_risk_items_when_only_shape_rule_hits() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    tmp_path = _case_dir("risk-rule-direct-apply")
    patch_path = tmp_path / "normalized.patch"
    patch_path.write_text(
        "\n".join(
            [
                "diff --git a/fs/demo.c b/fs/demo.c",
                "--- a/fs/demo.c",
                "+++ b/fs/demo.c",
                "@@ -1 +1 @@",
                "-if (old_guard)",
                "+if (new_guard)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    bundle = PatchBundle(
        task_id="TASK-RULE-003",
        cve_id="CVE-2099-0007",
        affected_files=["fs/demo.c"],
        normalized_patch_path=patch_path,
    )
    semantic_card = SemanticCard(
        bug_class="cve_fix",
        root_cause="条件收紧",
        touched_files=["fs/demo.c"],
        touched_functions=["demo_check"],
        must_keep_conditions=["demo_check: new_guard"],
    )

    registry = RiskRuleRegistry(repo_root)
    items = registry.evaluate(bundle, semantic_card=semantic_card)

    assert items == []
    assert registry.direct_apply_ready(bundle) is True
