"""Build a submission evidence bundle that includes ignored logs and binaries.

The bundle intentionally uses an explicit zip manifest instead of relying on
``git add`` so that ``*.log`` and generated ``*.ko`` files are preserved for
external validation without changing repository ignore rules.
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PATTERNS = (
    "*.ko",
    "report.json",
    "report.md",
    "validation_report.json",
    "rewritten.patch",
    "raw_patch.patch",
    "original.patch",
    "source_evidence.json",
    "build_summary.json",
    "failure_record.json",
    "*.log",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, default=Path("workspaces"))
    parser.add_argument("--evaluation-json", action="append", type=Path, default=[])
    parser.add_argument("--task-id", action="append", default=[])
    parser.add_argument("--output-zip", type=Path, default=Path("data/submission/patchweaver_submission_evidence_bundle.zip"))
    parser.add_argument("--manifest-output", type=Path, default=Path("data/submission/patchweaver_submission_evidence_manifest.json"))
    parser.add_argument("--include-evaluation-json", action="store_true", help="Also include source evaluation JSON files in the zip.")
    return parser.parse_args()


def task_ids_from_evaluation(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    ids: list[str] = []
    if isinstance(payload, dict):
        for item in payload.get("results", []) or payload.get("cases", []) or []:
            if isinstance(item, dict) and item.get("task_id"):
                ids.append(str(item["task_id"]))
    return ids


def collect_task_files(workspace_root: Path, task_id: str) -> dict[str, Any]:
    task_dir = workspace_root / task_id
    matched: list[Path] = []
    if task_dir.exists():
        for pattern in DEFAULT_PATTERNS:
            matched.extend(path for path in task_dir.rglob(pattern) if path.is_file())
    seen: set[Path] = set()
    unique = []
    for path in matched:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    required = {
        "ko": any(path.suffix == ".ko" for path in unique),
        "report_json": any(path.name == "report.json" for path in unique),
        "validation_report": any(path.name == "validation_report.json" for path in unique),
        "rewritten_patch": any(path.name == "rewritten.patch" for path in unique),
        "source_patch": any(path.name in {"raw_patch.patch", "original.patch"} for path in unique),
        "logs": any(path.suffix == ".log" for path in unique),
    }
    return {
        "task_id": task_id,
        "workspace_dir": str(task_dir),
        "workspace_exists": task_dir.exists(),
        "files": unique,
        "required": required,
        "missing_required": [key for key, present in required.items() if not present],
    }


def build_bundle(
    *,
    workspace_root: Path,
    evaluation_jsons: list[Path],
    task_ids: list[str],
    output_zip: Path,
    manifest_output: Path,
    include_evaluation_json: bool = False,
) -> dict[str, Any]:
    discovered = list(task_ids)
    for path in evaluation_jsons:
        discovered.extend(task_ids_from_evaluation(path))
    ordered_task_ids = list(dict.fromkeys(item for item in discovered if item))
    tasks = [collect_task_files(workspace_root, task_id) for task_id in ordered_task_ids]

    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if include_evaluation_json:
            for path in evaluation_jsons:
                if path.exists():
                    archive.write(path, f"evaluation/{path.name}")
        for task in tasks:
            for path in task["files"]:
                task_dir = workspace_root / task["task_id"]
                arcname = Path("workspaces") / task["task_id"] / path.relative_to(task_dir)
                archive.write(path, str(arcname).replace("\\", "/"))

    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workspace_root": str(workspace_root),
        "output_zip": str(output_zip),
        "evaluation_jsons": [str(path) for path in evaluation_jsons],
        "summary": {
            "task_count": len(tasks),
            "workspace_missing": sum(1 for item in tasks if not item["workspace_exists"]),
            "complete_tasks": sum(1 for item in tasks if not item["missing_required"]),
            "tasks_with_ko": sum(1 for item in tasks if item["required"]["ko"]),
            "tasks_with_logs": sum(1 for item in tasks if item["required"]["logs"]),
        },
        "tasks": [
            {
                "task_id": item["task_id"],
                "workspace_dir": item["workspace_dir"],
                "workspace_exists": item["workspace_exists"],
                "file_count": len(item["files"]),
                "required": item["required"],
                "missing_required": item["missing_required"],
            }
            for item in tasks
        ],
        "note": "The zip preserves .log and .ko files even when ignored by git.",
    }
    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    manifest_output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    args = parse_args()
    manifest = build_bundle(
        workspace_root=args.workspace_root,
        evaluation_jsons=args.evaluation_json,
        task_ids=args.task_id,
        output_zip=args.output_zip,
        manifest_output=args.manifest_output,
        include_evaluation_json=args.include_evaluation_json,
    )
    print(f"submission evidence bundle written: {manifest['output_zip']}")
    print(f"submission evidence manifest written: {args.manifest_output}")
    return 0 if manifest["summary"]["workspace_missing"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
