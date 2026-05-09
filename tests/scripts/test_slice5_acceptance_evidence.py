from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
VALIDATION_DIR = PROJECT_ROOT / "data" / "evaluations" / "validation_v0509"


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_slice5_holdout10_keeps_at_least_one_real_cve_full_smoke_passed() -> None:
    payload = _load_json(VALIDATION_DIR / "final_holdout10_full_run_v0509.json")
    manifest = _load_json(VALIDATION_DIR / "final_holdout10_evidence_manifest_v0509.json")
    results = payload["results"]

    passing_real_cves = [
        item
        for item in results
        if item["cve_id"].startswith("CVE-2024-")
        and item["run_status"] == "built"
        and item["build_exec_status"] == "executed"
        and item["validation_status"] == "passed"
        and item["failure_type"] == "none"
        and item["sample_bucket"] == "buildable_and_should_pass"
        and item["screening_tier"] == "positive_acceptance_confirmed"
    ]

    assert payload["summary"]["representative_success_rate"] == 1.0
    assert payload["summary"]["average_attempts"] == 1.0
    assert passing_real_cves, "Slice 5 needs at least one known positive CVE full-smoke pass"
    first_cve = passing_real_cves[0]["cve_id"]
    manifest_entry = next(entry for entry in manifest["entries"] if entry["cve_id"] == first_cve)
    assert manifest_entry["validation_status"] == "passed"
    assert manifest_entry["module_path"].endswith(".ko")
    assert manifest_entry["evidence_paths"]["patchweaver-*.ko"]


def test_slice5_positive_pool_evidence_does_not_count_template_unit_cases() -> None:
    full_run = _load_json(VALIDATION_DIR / "final_holdout10_full_run_v0509.json")
    manifest = _load_json(VALIDATION_DIR / "final_holdout10_evidence_manifest_v0509.json")

    assert manifest["complete"] == manifest["total"]
    assert manifest["partial"] == 0
    assert manifest["missing"] == 0

    positive_ids = set(full_run["summary"]["positive_pool_candidates"])
    manifest_ids = {entry["cve_id"] for entry in manifest["entries"]}
    forbidden_prefixes = ("CVE-UNIT-", "CVE-TEST-", "CVE-2099-")

    assert positive_ids
    assert all(cve_id.startswith("CVE-2024-") for cve_id in positive_ids)
    assert not any(cve_id.startswith(forbidden_prefixes) for cve_id in positive_ids)
    assert not any(cve_id.startswith(forbidden_prefixes) for cve_id in manifest_ids)
    assert not any("complex-route" in item["task_id"] for item in full_run["results"])
