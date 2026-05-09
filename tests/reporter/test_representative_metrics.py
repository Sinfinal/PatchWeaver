from __future__ import annotations

import json
from pathlib import Path

from patchweaver.reporter.representative_metrics import (
    build_representative_metrics_report,
    write_representative_metrics_report,
)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def test_representative_metrics_report_merges_holdout_and_manifest_evidence(tmp_path: Path) -> None:
    holdout_path = _write_json(
        tmp_path / "holdout.json",
        {
            "summary": {"representative_total": 2},
            "results": [
                {
                    "cve_id": "CVE-2099-0001",
                    "task_id": "holdout-0001",
                    "run_status": "built",
                    "validation_status": "passed",
                    "selected_route": "direct_apply_patch",
                    "model_name": "qwen-plus",
                    "module_path": "workspaces/holdout-0001/attempts/001/output/demo.ko",
                    "rag_seed_hit": True,
                    "rag_seed_group": "rag-linux-kernel-2024-batch100",
                    "rag_subsystem": "drivers/net",
                    "rag_summary": "demo fix",
                    "run_attempts": [{"run_index": 1, "run_status": "built", "validation_status": "passed"}],
                    "validation_report": {
                        "load_result": {"status": "passed", "log_path": "workspaces/holdout-0001/logs/load.log"},
                        "unload_result": {"status": "passed", "log_path": "workspaces/holdout-0001/logs/unload.log"},
                        "smoke_result": {"status": "passed", "log_path": "workspaces/holdout-0001/logs/smoke.log"},
                        "selftest_result": {"status": "passed", "log_path": "workspaces/holdout-0001/logs/selftest.log"},
                    },
                },
                {
                    "cve_id": "CVE-2099-0002",
                    "task_id": "holdout-0002",
                    "run_status": "failed",
                    "validation_status": "failed",
                    "run_failure_type": "build_failed",
                    "selected_route": "minimal_livepatch_wrap",
                    "run_attempts": [
                        {"run_index": 1, "run_status": "failed"},
                        {"run_index": 2, "run_status": "failed"},
                    ],
                },
            ],
        },
    )
    manifest_path = _write_json(
        tmp_path / "manifest.json",
        {
            "entries": [
                {
                    "cve_id": "CVE-2099-0001",
                    "status": "complete",
                    "module_path": "workspaces/holdout-0001/attempts/001/output/demo.ko",
                    "validation_status": "passed",
                    "evidence_paths": {
                        "patchweaver-*.ko": ["workspaces/holdout-0001/attempts/001/output/demo.ko"],
                        "validation_report.json": "workspaces/holdout-0001/attempts/001/diagnostics/validation_report.json",
                        "report.json": "workspaces/holdout-0001/reports/report.json",
                    },
                }
            ]
        },
    )

    report = build_representative_metrics_report(
        holdout_path=holdout_path,
        evidence_manifest_path=manifest_path,
        target_success_rate=0.60,
    )

    assert report["metrics"]["representative_total"] == 2
    assert report["metrics"]["representative_success_rate"] == 0.5
    assert report["metrics"]["average_attempts"] == 1.5
    assert report["metrics"]["success_gap_to_60_percent"] == 0.1
    assert report["failure_buckets"] == {"success": 1, "build_failed": 1}
    assert report["model_rag_summary"]["rag_seed_hits"] == 1
    assert report["model_rag_summary"]["selected_route_counts"] == {
        "direct_apply_patch": 1,
        "minimal_livepatch_wrap": 1,
    }
    assert report["model_rag_summary"]["model_counts"] == {"qwen-plus": 1}
    assert report["model_rag_summary"]["model_missing"] == 1
    assert report["target_gap"]["status"] == "below_target"
    assert "60%" in report["target_gap"]["explanation"]
    success_case = report["cases"][0]
    assert success_case["model_rag"]["rag_seed_hit"] is True
    assert success_case["model_rag"]["rag_subsystem"] == "drivers/net"
    assert success_case["evidence"]["ko"]["path"].endswith("demo.ko")
    assert success_case["evidence"]["load"]["status"] == "passed"
    assert success_case["evidence"]["unload"]["path"].endswith("unload.log")
    assert success_case["evidence"]["smoke"]["path"].endswith("smoke.log")
    assert success_case["evidence"]["selftest"]["path"].endswith("selftest.log")
    assert success_case["evidence_paths"]["validation_report.json"].endswith("validation_report.json")
    assert success_case["evidence_paths"]["report.json"].endswith("report.json")


def test_representative_metrics_writer_outputs_json_and_markdown(tmp_path: Path) -> None:
    holdout_path = _write_json(
        tmp_path / "holdout.json",
        {
            "results": [
                {
                    "cve_id": "CVE-2099-0001",
                    "task_id": "holdout-0001",
                    "run_status": "built",
                    "validation_status": "passed",
                    "run_attempts": [{"run_index": 1}],
                    "validation_report": {
                        "load_result": {"status": "passed", "log_path": "load.log"},
                        "unload_result": {"status": "passed", "log_path": "unload.log"},
                        "smoke_result": {"status": "passed", "log_path": "smoke.log"},
                        "selftest_result": {"status": "passed", "log_path": "selftest.log"},
                    },
                }
            ]
        },
    )
    json_output = tmp_path / "representative_metrics.json"
    md_output = tmp_path / "representative_metrics.md"

    write_representative_metrics_report(
        holdout_path=holdout_path,
        evidence_manifest_path=None,
        output_json_path=json_output,
        output_md_path=md_output,
        target_success_rate=0.60,
    )

    payload = json.loads(json_output.read_text(encoding="utf-8"))
    markdown = md_output.read_text(encoding="utf-8")
    assert payload["metrics"]["representative_total"] == 1
    assert "representative_success_rate" in markdown
    assert ".ko/load/unload/smoke/selftest" in markdown
    assert "Failure Buckets" in markdown
    assert "Model/RAG Participation" in markdown
