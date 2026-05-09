from __future__ import annotations

import json
from pathlib import Path

from patchweaver.reporter.positive_pool_manifest import build_positive_pool_evidence_manifest


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_text(path: Path, content: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _fixture(path: Path) -> Path:
    payload = [
        {
            "fixture_id": "challenge-positive-cve-2024-26675",
            "cve_id": "CVE-2024-26675",
            "expected_artifacts": [
                "build_summary.json",
                "validation_report.json",
                "repair_intent.json",
                "rewritten.patch",
                "semantic_guard.json",
                "report.json",
                "patchweaver-*.ko",
            ],
        }
    ]
    _write_json(path, payload)
    return path


def test_manifest_collects_complete_workspace_evidence(tmp_path: Path) -> None:
    fixture_path = _fixture(tmp_path / "pool.json")
    task_dir = tmp_path / "project" / "workspaces" / "TASK-CVE-2024-26675"
    attempt_dir = task_dir / "attempts" / "001"
    _write_json(task_dir / "task_context.json", {"cve_id": "CVE-2024-26675"})
    _write_json(task_dir / "reports" / "report.json", {"task_summary": {"cve_id": "CVE-2024-26675"}})
    _write_json(attempt_dir / "artifacts" / "build_summary.json", {"status": "built"})
    _write_json(attempt_dir / "artifacts" / "validation_report.json", {"status": "passed"})
    _write_json(attempt_dir / "artifacts" / "repair_intent.json", {"cve_id": "CVE-2024-26675"})
    _write_json(attempt_dir / "artifacts" / "semantic_guard.json", {"status": "passed"})
    _write_text(attempt_dir / "rewrite" / "rewritten.patch", "diff --git a/x b/x\n")
    _write_text(attempt_dir / "output" / "patchweaver-test.ko", "fake ko")

    manifest = build_positive_pool_evidence_manifest(
        fixture_path=fixture_path,
        workspace_root=tmp_path / "project",
        include_generated_at=False,
    )

    entry = manifest["entries"][0]
    assert manifest["complete"] == 1
    assert entry["cve_id"] == "CVE-2024-26675"
    assert entry["status"] == "complete"
    assert entry["missing_artifacts"] == []
    assert entry["module_path"].endswith("patchweaver-test.ko")
    assert entry["module_vermagic"] is None
    assert entry["validation_status"] == "passed"
    assert entry["evidence_paths"]["build_summary.json"].endswith("build_summary.json")
    assert entry["evidence_paths"]["patchweaver-*.ko"][0].endswith("patchweaver-test.ko")


def test_manifest_accepts_workspace_directory_as_root(tmp_path: Path) -> None:
    fixture_path = _fixture(tmp_path / "pool.json")
    task_dir = tmp_path / "project" / "workspaces" / "TASK-CVE-2024-26675"
    attempt_dir = task_dir / "attempts" / "001"
    _write_json(task_dir / "task_context.json", {"cve_id": "CVE-2024-26675"})
    _write_json(attempt_dir / "artifacts" / "build_summary.json", {"status": "built"})

    manifest = build_positive_pool_evidence_manifest(
        fixture_path=fixture_path,
        workspace_root=tmp_path / "project" / "workspaces",
        include_generated_at=False,
    )

    entry = manifest["entries"][0]
    assert manifest["partial"] == 1
    assert entry["status"] == "partial"
    assert entry["evidence_paths"]["build_summary.json"].endswith("build_summary.json")


def test_manifest_marks_missing_artifacts_without_workspace_evidence(tmp_path: Path) -> None:
    fixture_path = _fixture(tmp_path / "pool.json")

    manifest = build_positive_pool_evidence_manifest(
        fixture_path=fixture_path,
        workspace_root=tmp_path / "project",
        include_generated_at=False,
    )

    entry = manifest["entries"][0]
    assert manifest["missing"] == 1
    assert entry["status"] == "missing"
    assert entry["module_path"] is None
    assert entry["validation_status"] is None
    assert entry["evidence_paths"] == {}
    assert entry["missing_artifacts"] == [
        "build_summary.json",
        "validation_report.json",
        "repair_intent.json",
        "rewritten.patch",
        "semantic_guard.json",
        "report.json",
        "patchweaver-*.ko",
    ]


def test_manifest_marks_partial_when_some_artifacts_exist(tmp_path: Path) -> None:
    fixture_path = _fixture(tmp_path / "pool.json")
    task_dir = tmp_path / "project" / "workspaces" / "TASK-CVE-2024-26675"
    _write_json(task_dir / "task_context.json", {"cve_id": "CVE-2024-26675"})
    _write_json(task_dir / "attempts" / "001" / "artifacts" / "validation_report.json", {"status": "pending"})

    manifest = build_positive_pool_evidence_manifest(
        fixture_path=fixture_path,
        workspace_root=tmp_path / "project",
        include_generated_at=False,
    )

    entry = manifest["entries"][0]
    assert manifest["partial"] == 1
    assert entry["status"] == "partial"
    assert entry["validation_status"] == "pending"
    assert "validation_report.json" not in entry["missing_artifacts"]
    assert "build_summary.json" in entry["missing_artifacts"]
