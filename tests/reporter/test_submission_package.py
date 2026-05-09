from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from patchweaver.reporter.submission_package import build_submission_package


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_submission_package_summarizes_p2_inputs_without_secrets(tmp_path: Path) -> None:
    positive_evidence = tmp_path / "positive_pool_evidence_manifest.json"
    holdout_report = tmp_path / "holdout_dry_run.json"
    demo_manifest = tmp_path / "demo_manifest.json"
    output_manifest = tmp_path / "submission_manifest.json"
    output_md = tmp_path / "submission_summary.md"

    _write_json(
        positive_evidence,
        {
            "total": 2,
            "complete": 1,
            "partial": 1,
            "missing": 0,
            "entries": [
                {
                    "cve_id": "CVE-2099-0001",
                    "status": "complete",
                    "validation_status": "passed",
                    "module_path": "workspaces/TASK-1/output/patchweaver.ko",
                    "module_vermagic": "6.6.102-5.2.an23.x86_64 SMP",
                    "missing_artifacts": [],
                },
                {
                    "cve_id": "CVE-2099-0002",
                    "status": "partial",
                    "validation_status": "pending",
                    "missing_artifacts": ["patchweaver-*.ko"],
                },
            ],
        },
    )
    _write_json(
        holdout_report,
        {
            "status": "passed",
            "mode": "dry-run",
            "dry_run": True,
            "fixture_name": "p2_holdout",
            "total_cases": 1,
            "agent_decision_summary": {
                "repair_intent_cases": 1,
                "strategy_switch_cases": 1,
                "failure_attribution_cases": 1,
            },
            "cases": [
                {
                    "blind_id": "HOLDOUT-001-deadbeef",
                    "mode": "dry-run",
                    "bucket": "buildable_and_should_pass",
                    "planned_actions": ["load_fixture", "plan_attempt", "skip_kpatch_build"],
                    "agent_decision_surface": {
                        "repair_intent": {"present": True},
                        "strategy_switch": {"present": True, "switched": True},
                        "failure_attribution": {"present": True},
                    },
                }
            ],
        },
    )
    _write_json(
        demo_manifest,
        {
            "summary": {
                "positive_evidence_count": 2,
                "workspace_report_count": 3,
                "standalone_report_count": 1,
                "ko_artifact_count": 1,
                "repair_intent_count": 2,
                "strategy_switch_count": 1,
                "failure_attribution_count": 1,
            }
        },
    )

    manifest = build_submission_package(
        positive_evidence_path=positive_evidence,
        holdout_report_path=holdout_report,
        demo_manifest_path=demo_manifest,
        output_manifest_path=output_manifest,
        output_markdown_path=output_md,
        bailian_entrypoint="TODO_BAILIAN_URL",
        bailian_env_vars=("BAILIAN_API_KEY", "BAILIAN_APP_ID"),
        include_generated_at=False,
    )

    assert manifest["confirmed_pool"]["total"] == 2
    assert manifest["representative_metrics"]["positive_evidence_completion_rate"] == 0.5
    assert manifest["representative_metrics"]["workspace_report_count"] == 3
    assert manifest["p2_holdout"]["status"] == "passed"
    assert manifest["p2_holdout"]["blind_identities_preserved"] is True
    assert manifest["p2_holdout"]["agent_decision_summary"]["repair_intent_cases"] == 1
    assert manifest["agent_decision_evidence"]["demo"]["repair_intent_count"] == 2
    assert manifest["agent_decision_evidence"]["demo"]["strategy_switch_count"] == 1
    assert manifest["agent_decision_evidence"]["holdout"]["failure_attribution_cases"] == 1
    assert manifest["bailian_entrypoint"]["value"] == "TODO_BAILIAN_URL"
    assert [item["name"] for item in manifest["bailian_entrypoint"]["required_environment"]] == [
        "BAILIAN_API_KEY",
        "BAILIAN_APP_ID",
    ]
    assert output_manifest.exists()
    markdown = output_md.read_text(encoding="utf-8")
    assert "CVE-2099-0001" in markdown
    assert "P2 Holdout" in markdown
    assert "Agent Decision Evidence" in markdown
    assert "RepairIntent count: 2" in markdown
    assert "BAILIAN_API_KEY" in markdown
    assert "secret values are not read or written" in markdown


def test_generate_submission_package_cli_writes_outputs(tmp_path: Path) -> None:
    positive_evidence = tmp_path / "positive.json"
    holdout_report = tmp_path / "holdout.json"
    demo_manifest = tmp_path / "demo.json"
    output_manifest = tmp_path / "submission_manifest.json"
    output_md = tmp_path / "submission_summary.md"

    _write_json(
        positive_evidence,
        {
            "total": 1,
            "complete": 1,
            "partial": 0,
            "missing": 0,
            "entries": [
                {
                    "cve_id": "CVE-2099-1001",
                    "status": "complete",
                    "validation_status": "passed",
                    "module_path": "demo.ko",
                    "missing_artifacts": [],
                }
            ],
        },
    )
    _write_json(
        holdout_report,
        {
            "status": "passed",
            "mode": "metadata",
            "dry_run": True,
            "total_cases": 1,
            "agent_decision_summary": {
                "repair_intent_cases": 1,
                "strategy_switch_cases": 0,
                "failure_attribution_cases": 0,
            },
            "cases": [{"blind_id": "HOLDOUT-001-abc12345", "planned_actions": ["metadata_only"]}],
        },
    )
    _write_json(
        demo_manifest,
        {
            "summary": {
                "workspace_report_count": 1,
                "ko_artifact_count": 1,
                "repair_intent_count": 1,
                "strategy_switch_count": 0,
                "failure_attribution_count": 0,
            }
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "scripts/generate_submission_package.py",
            "--positive-evidence",
            str(positive_evidence),
            "--holdout-report",
            str(holdout_report),
            "--demo-manifest",
            str(demo_manifest),
            "--output-manifest",
            str(output_manifest),
            "--output-md",
            str(output_md),
            "--bailian-entrypoint",
            "TODO_BAILIAN_ENTRY",
            "--bailian-env",
            "BAILIAN_API_KEY",
            "--bailian-env",
            "BAILIAN_APP_ID",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    manifest = json.loads(output_manifest.read_text(encoding="utf-8"))
    assert manifest["confirmed_pool"]["complete"] == 1
    assert manifest["p2_holdout"]["dry_run"] is True
    assert manifest["agent_decision_evidence"]["demo"]["repair_intent_count"] == 1
    assert manifest["bailian_entrypoint"]["value"] == "TODO_BAILIAN_ENTRY"
    assert "submission manifest written:" in proc.stdout
    assert "CVE-2099-1001" in output_md.read_text(encoding="utf-8")
