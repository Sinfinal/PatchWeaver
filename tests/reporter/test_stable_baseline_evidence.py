from __future__ import annotations

import json
from pathlib import Path

from patchweaver.reporter.stable_baseline_evidence import build_stable_baseline_evidence_manifest


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_build_stable_baseline_evidence_manifest_checks_filesystem(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "stable-baselines" / "abc"
    (baseline_dir / "scripts").mkdir(parents=True)
    (baseline_dir / "Makefile").write_text("VERSION = 6\n", encoding="utf-8")
    (baseline_dir / "scripts" / "setlocalversion").write_text("#!/bin/sh\n", encoding="utf-8")
    (baseline_dir / ".config").write_text("CONFIG_TEST=y\n", encoding="utf-8")
    source_head = "a" * 40
    _write_json(
        baseline_dir / "patchweaver_stable_baseline.json",
        {
            "stable_git_dir": str(tmp_path / "linux-stable"),
            "baseline_ref": "deadbeef^",
            "output_dir": str(baseline_dir),
            "git_head": source_head,
        },
    )

    evaluation = tmp_path / "eval.json"
    output_json = tmp_path / "manifest.json"
    output_md = tmp_path / "manifest.md"
    _write_json(
        evaluation,
        {
            "results": [
                {
                    "cve_id": "CVE-2099-0001",
                    "sample_bucket": "buildable_and_should_pass",
                    "stable_baseline_ready": True,
                    "stable_baseline_preparation": {
                        "status": "prepared",
                        "baseline_ref": "deadbeef^",
                        "output_dir": str(baseline_dir),
                    },
                    "failure_type": "none",
                    "build_status": "built",
                    "validation_status": "passed",
                }
            ]
        },
    )

    manifest = build_stable_baseline_evidence_manifest(
        [evaluation],
        output_json=output_json,
        output_md=output_md,
    )

    assert manifest["total"] == 1
    assert manifest["prepared"] == 1
    assert manifest["complete"] == 1
    assert manifest["git_source_traceable"] == 1
    entry = manifest["entries"][0]
    assert entry["cve_id"] == "CVE-2099-0001"
    assert entry["baseline_ref"] == "deadbeef^"
    assert entry["complete"] is True
    assert entry["git_source_traceable"] is True
    assert entry["source_manifest_git_head"] == source_head
    assert entry["source_provenance_status"] == "git_worktree_traceable"
    assert "CVE-2099-0001" in output_md.read_text(encoding="utf-8")


def test_build_stable_baseline_evidence_manifest_marks_incomplete_missing_files(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "stable-baselines" / "missing"
    baseline_dir.mkdir(parents=True)
    evaluation = tmp_path / "eval.json"
    output_json = tmp_path / "manifest.json"
    output_md = tmp_path / "manifest.md"
    _write_json(
        evaluation,
        {
            "results": [
                {
                    "cve_id": "CVE-2099-0002",
                    "stable_baseline_ready": True,
                    "stable_baseline_preparation": {"status": "prepared", "output_dir": str(baseline_dir)},
                }
            ]
        },
    )

    manifest = build_stable_baseline_evidence_manifest(
        [evaluation],
        output_json=output_json,
        output_md=output_md,
    )

    assert manifest["total"] == 1
    assert manifest["complete"] == 0
    assert manifest["incomplete"] == 1
    assert manifest["entries"][0]["makefile_exists"] is False


def test_build_stable_baseline_evidence_manifest_separates_snapshot_from_git_source(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "stable-baselines" / "snapshot"
    (baseline_dir / "scripts").mkdir(parents=True)
    (baseline_dir / "Makefile").write_text("VERSION = 6\n", encoding="utf-8")
    (baseline_dir / "scripts" / "setlocalversion").write_text("#!/bin/sh\n", encoding="utf-8")
    (baseline_dir / ".config").write_text("CONFIG_TEST=y\n", encoding="utf-8")
    _write_json(
        baseline_dir / "patchweaver_stable_baseline.json",
        {
            "stable_git_dir": str(tmp_path / "missing-stable-repo"),
            "baseline_ref": "cafebabe^",
            "output_dir": str(baseline_dir),
            "git_head": None,
        },
    )
    evaluation = tmp_path / "eval.json"
    output_json = tmp_path / "manifest.json"
    output_md = tmp_path / "manifest.md"
    _write_json(
        evaluation,
        {
            "results": [
                {
                    "cve_id": "CVE-2099-0003",
                    "stable_baseline_ready": True,
                    "stable_baseline_preparation": {
                        "status": "prepared",
                        "baseline_ref": "cafebabe^",
                        "output_dir": str(baseline_dir),
                    },
                }
            ]
        },
    )

    manifest = build_stable_baseline_evidence_manifest(
        [evaluation],
        output_json=output_json,
        output_md=output_md,
    )

    entry = manifest["entries"][0]
    assert manifest["complete"] == 1
    assert manifest["git_source_traceable"] == 0
    assert manifest["git_source_untraceable"] == 1
    assert entry["complete"] is True
    assert entry["git_source_traceable"] is False
    assert entry["source_manifest_matches_request"] is True
    assert entry["source_provenance_status"] == "snapshot_or_non_git_source"
