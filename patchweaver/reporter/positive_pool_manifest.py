"""Evidence manifest builder for the confirmed positive challenge pool."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXPECTED_ARTIFACTS = (
    "build_summary.json",
    "validation_report.json",
    "repair_intent.json",
    "rewritten.patch",
    "semantic_guard.json",
    "report.json",
    "patchweaver-*.ko",
)

TASK_METADATA_FILES = (
    "task_context.json",
    "reports/report.json",
    "input/patch_bundle.json",
)


def build_positive_pool_evidence_manifest(
    *,
    fixture_path: Path,
    workspace_root: Path,
    include_generated_at: bool = True,
) -> dict[str, Any]:
    """Build a JSON-serializable manifest for confirmed positive pool fixtures."""

    fixtures = _load_fixture_entries(fixture_path)
    task_dirs_by_cve = _index_task_dirs_by_cve(workspace_root)
    entries = [
        _build_entry(fixture=fixture, task_dirs=task_dirs_by_cve.get(str(fixture["cve_id"]), []))
        for fixture in fixtures
    ]
    manifest: dict[str, Any] = {
        "fixture_path": str(fixture_path),
        "workspace_root": str(workspace_root),
        "total": len(entries),
        "complete": sum(1 for entry in entries if entry["status"] == "complete"),
        "partial": sum(1 for entry in entries if entry["status"] == "partial"),
        "missing": sum(1 for entry in entries if entry["status"] == "missing"),
        "entries": entries,
    }
    if include_generated_at:
        manifest["generated_at"] = datetime.now(timezone.utc).isoformat()
    return manifest


def write_positive_pool_evidence_manifest(
    *,
    fixture_path: Path,
    workspace_root: Path,
    output_path: Path,
) -> Path:
    """Build and write the positive pool evidence manifest."""

    manifest = build_positive_pool_evidence_manifest(
        fixture_path=fixture_path,
        workspace_root=workspace_root,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path


def _load_fixture_entries(fixture_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"positive pool fixture must be a list: {fixture_path}")
    entries: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict) or not item.get("cve_id"):
            raise ValueError(f"fixture entry is missing cve_id: {item!r}")
        entries.append(item)
    return entries


def _index_task_dirs_by_cve(workspace_root: Path) -> dict[str, list[Path]]:
    if not workspace_root.exists():
        return {}

    candidates: set[Path] = set()
    workspace_dir = workspace_root / "workspaces"
    if workspace_dir.exists():
        candidates.update(path for path in workspace_dir.iterdir() if path.is_dir())
    elif workspace_root.name == "workspaces":
        candidates.update(path for path in workspace_root.iterdir() if path.is_dir())
    if any((workspace_root / rel).exists() for rel in TASK_METADATA_FILES):
        candidates.add(workspace_root)

    by_cve: dict[str, list[Path]] = {}
    for task_dir in sorted(candidates):
        cve_id = _read_task_cve_id(task_dir)
        if not cve_id:
            continue
        by_cve.setdefault(cve_id, []).append(task_dir)
    return by_cve


def _read_task_cve_id(task_dir: Path) -> str | None:
    for rel_path in TASK_METADATA_FILES:
        path = task_dir / rel_path
        payload = _read_json(path)
        if not isinstance(payload, dict):
            continue
        cve_id = payload.get("cve_id")
        if not cve_id and isinstance(payload.get("task_summary"), dict):
            cve_id = payload["task_summary"].get("cve_id")
        if cve_id:
            return str(cve_id)
    return None


def _build_entry(*, fixture: dict[str, Any], task_dirs: list[Path]) -> dict[str, Any]:
    evidence = _collect_evidence(task_dirs)
    expected = tuple(fixture.get("expected_artifacts") or EXPECTED_ARTIFACTS)
    missing = [artifact for artifact in expected if not _has_artifact(evidence, artifact)]
    module_path = _first_path(evidence.get("patchweaver-*.ko"))
    entry = {
        "cve_id": str(fixture["cve_id"]),
        "status": _entry_status(evidence, missing, expected),
        "missing_artifacts": missing,
        "module_path": module_path,
        "module_vermagic": _read_module_vermagic(Path(module_path)) if module_path else None,
        "validation_status": _read_validation_status(_first_path(evidence.get("validation_report.json"))),
        "evidence_paths": evidence,
    }
    return entry


def _collect_evidence(task_dirs: list[Path]) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    for artifact in EXPECTED_ARTIFACTS:
        paths: list[Path]
        if artifact == "patchweaver-*.ko":
            paths = _find_paths(task_dirs, "*.ko")
        elif artifact == "report.json":
            paths = _find_paths(task_dirs, "report.json", preferred_parts=("reports",))
        elif artifact == "rewritten.patch":
            paths = _find_paths(task_dirs, artifact, preferred_parts=("rewrite",))
        else:
            paths = _find_paths(task_dirs, artifact)
        if paths:
            evidence[artifact] = [str(path) for path in paths] if artifact == "patchweaver-*.ko" else str(paths[0])
    return evidence


def _find_paths(task_dirs: list[Path], pattern: str, preferred_parts: tuple[str, ...] = ()) -> list[Path]:
    paths: list[Path] = []
    for task_dir in task_dirs:
        paths.extend(path for path in task_dir.rglob(pattern) if path.is_file())
    paths.sort(key=lambda path: (_preferred_rank(path, preferred_parts), -path.stat().st_mtime, str(path)))
    return paths


def _preferred_rank(path: Path, preferred_parts: tuple[str, ...]) -> int:
    parts = set(path.parts)
    return 0 if any(part in parts for part in preferred_parts) else 1


def _has_artifact(evidence: dict[str, Any], artifact: str) -> bool:
    if artifact in evidence:
        return True
    if artifact.endswith(".ko") or artifact == ".ko":
        return bool(evidence.get("patchweaver-*.ko"))
    return False


def _entry_status(evidence: dict[str, Any], missing: list[str], expected: tuple[str, ...]) -> str:
    if not evidence:
        return "missing"
    if not missing and len(evidence) >= len(expected):
        return "complete"
    return "partial"


def _read_validation_status(path: str | None) -> str | None:
    if not path:
        return None
    payload = _read_json(Path(path))
    if not isinstance(payload, dict):
        return None
    status = payload.get("status")
    return str(status) if status is not None else None


def _read_module_vermagic(module_path: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["modinfo", "-F", "vermagic", str(module_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    vermagic = completed.stdout.strip()
    return vermagic or None


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _first_path(value: Any) -> str | None:
    if isinstance(value, list) and value:
        return str(value[0])
    if isinstance(value, str):
        return value
    return None
