from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

from scripts.build_submission_evidence_bundle import build_bundle


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _write(path: Path, text: str = "{}") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_build_submission_evidence_bundle_preserves_ignored_logs_and_kernel_modules(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspaces"
    task_dir = workspace_root / "task-1"
    _write(task_dir / "attempts" / "001" / "output" / "patchweaver-demo.ko", "binary-placeholder")
    _write(task_dir / "attempts" / "001" / "artifacts" / "validation_report.json")
    _write(task_dir / "attempts" / "001" / "artifacts" / "build_summary.json")
    _write(task_dir / "attempts" / "001" / "artifacts" / "rewritten.patch", "diff --git a/demo b/demo\n")
    _write(task_dir / "input" / "raw_patch.patch", "diff --git a/original b/original\n")
    _write(task_dir / "reports" / "report.json")
    _write(task_dir / "reports" / "report.md", "# report\n")
    _write(task_dir / "logs" / "build.log", "kpatch-build log\n")
    evaluation = tmp_path / "evaluation.json"
    _write(evaluation, json.dumps({"results": [{"task_id": "task-1"}]}))

    output_zip = tmp_path / "bundle.zip"
    manifest_output = tmp_path / "manifest.json"

    manifest = build_bundle(
        workspace_root=workspace_root,
        evaluation_jsons=[evaluation],
        task_ids=[],
        output_zip=output_zip,
        manifest_output=manifest_output,
        include_evaluation_json=True,
    )

    assert manifest["summary"]["task_count"] == 1
    assert manifest["summary"]["complete_tasks"] == 1
    assert manifest["summary"]["tasks_with_ko"] == 1
    assert manifest["summary"]["tasks_with_logs"] == 1
    with zipfile.ZipFile(output_zip) as archive:
        names = set(archive.namelist())
    assert "workspaces/task-1/attempts/001/output/patchweaver-demo.ko" in names
    assert "workspaces/task-1/logs/build.log" in names
    assert "evaluation/evaluation.json" in names


def test_build_submission_evidence_bundle_cli_reports_missing_workspace(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspaces"
    output_zip = tmp_path / "bundle.zip"
    manifest_output = tmp_path / "manifest.json"

    proc = subprocess.run(
        [
            sys.executable,
            "scripts/build_submission_evidence_bundle.py",
            "--workspace-root",
            str(workspace_root),
            "--task-id",
            "missing-task",
            "--output-zip",
            str(output_zip),
            "--manifest-output",
            str(manifest_output),
        ],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 1
    manifest = json.loads(manifest_output.read_text(encoding="utf-8"))
    assert manifest["summary"]["workspace_missing"] == 1
    assert manifest["tasks"][0]["missing_required"]
