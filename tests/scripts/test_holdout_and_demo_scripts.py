from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_run_holdout_blind_metadata_does_not_reveal_cve_by_default(tmp_path: Path) -> None:
    fixture = tmp_path / "holdout.json"
    output = tmp_path / "holdout_summary.json"
    fixture.write_text(
        json.dumps(
            {
                "fixture_name": "final_style_holdout",
                "cases": [
                    {
                        "cve_id": "CVE-2099-2001",
                        "bucket": "buildable_and_should_pass",
                        "expected_artifacts": ["repair_intent.json", "rewritten.patch"],
                        "repair_intent": {"recommended_strategy": "semantic_guard"},
                        "selected_strategy": "smpl_template",
                        "failure_type": "compile_failed",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            "scripts/run_holdout_blind.py",
            "--fixture",
            str(fixture),
            "--output",
            str(output),
            "--mode",
            "metadata",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    summary = json.loads(output.read_text(encoding="utf-8"))
    assert summary["status"] == "passed"
    assert summary["dry_run"] is True
    assert summary["total_cases"] == 1
    assert summary["cases"][0]["blind_id"].startswith("HOLDOUT-")
    assert "cve_id" not in summary["cases"][0]
    assert summary["cases"][0]["planned_actions"] == ["metadata_only"]
    assert summary["agent_decision_summary"]["repair_intent_cases"] == 1
    assert summary["agent_decision_summary"]["strategy_switch_cases"] == 1
    assert summary["agent_decision_summary"]["failure_attribution_cases"] == 1
    assert summary["cases"][0]["agent_decision_surface"]["repair_intent"]["present"] is True
    assert summary["cases"][0]["agent_decision_surface"]["strategy_switch"]["present"] is True
    assert summary["cases"][0]["agent_decision_surface"]["failure_attribution"]["present"] is True


def test_generate_demo_report_writes_manifest_and_markdown(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspaces"
    reports_root = tmp_path / "reports"
    evidence_path = tmp_path / "positive_evidence.json"
    output_md = tmp_path / "demo_report.md"
    output_manifest = tmp_path / "submission_manifest.json"

    attempt_dir = workspace_root / "TASK-DEMO-001" / "attempts" / "001"
    (attempt_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    (workspace_root / "TASK-DEMO-001" / "reports").mkdir(parents=True, exist_ok=True)
    reports_root.mkdir(parents=True, exist_ok=True)
    (attempt_dir / "artifacts" / "demo.ko").write_text("fake ko\n", encoding="utf-8")
    (attempt_dir / "artifacts" / "validation_report.json").write_text(
        json.dumps({"status": "passed", "load": "passed", "unload": "passed"}),
        encoding="utf-8",
    )
    (workspace_root / "TASK-DEMO-001" / "analysis").mkdir(parents=True, exist_ok=True)
    (attempt_dir / "rewrite").mkdir(parents=True, exist_ok=True)
    (attempt_dir / "logs").mkdir(parents=True, exist_ok=True)
    (workspace_root / "TASK-DEMO-001" / "analysis" / "repair_intent.json").write_text(
        json.dumps({"recommended_strategy": "semantic_guard", "root_cause": "missing guard"}),
        encoding="utf-8",
    )
    (attempt_dir / "rewrite" / "rewrite_plan.json").write_text(
        json.dumps(
            {
                "selected_recipe": "smpl_primary_rewrite",
                "selected_strategy": "semantic_guard",
                "selection_reason": "intent matched recipe",
            }
        ),
        encoding="utf-8",
    )
    (attempt_dir / "logs" / "failure_record.json").write_text(
        json.dumps({"failure_type": "none", "summary": "no failure after validation"}),
        encoding="utf-8",
    )
    (workspace_root / "TASK-DEMO-001" / "reports" / "report.json").write_text(
        json.dumps({"task_id": "TASK-DEMO-001", "cve_id": "CVE-2099-3001", "status": "passed"}),
        encoding="utf-8",
    )
    evidence_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "cve_id": "CVE-2099-3001",
                        "module_path": str(attempt_dir / "artifacts" / "demo.ko"),
                        "module_vermagic": "6.6.102-5.2.an23.x86_64 SMP",
                        "validation_report_path": str(attempt_dir / "artifacts" / "validation_report.json"),
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            "scripts/generate_demo_report.py",
            "--workspace-root",
            str(workspace_root),
            "--reports-root",
            str(reports_root),
            "--positive-evidence",
            str(evidence_path),
            "--output-md",
            str(output_md),
            "--manifest-output",
            str(output_manifest),
        ],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    manifest = json.loads(output_manifest.read_text(encoding="utf-8"))
    assert manifest["summary"]["positive_evidence_count"] == 1
    assert manifest["summary"]["ko_artifact_count"] == 1
    assert manifest["summary"]["workspace_report_count"] == 1
    assert manifest["summary"]["repair_intent_count"] == 1
    assert manifest["summary"]["strategy_switch_count"] == 0
    assert manifest["summary"]["failure_attribution_count"] == 1
    assert manifest["workspace_reports"][0]["agent_decision_summary"]["repair_intent"]["present"] is True
    assert manifest["workspace_reports"][0]["agent_decision_summary"]["failure_attribution"]["failure_type"] == "none"
    assert manifest["artifacts"]["demo_report_md"] == str(output_md)
    markdown = output_md.read_text(encoding="utf-8")
    assert "CVE-2099-3001" in markdown
    assert "Agent Decision Evidence" in markdown
