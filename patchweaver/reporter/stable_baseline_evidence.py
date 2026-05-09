"""Stable source baseline evidence manifest builder."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class StableBaselineEvidence:
    cve_id: str
    baseline_ref: str | None
    status: str
    output_dir: str | None
    stable_baseline_ready: bool
    source_manifest_exists: bool
    makefile_exists: bool
    setlocalversion_exists: bool
    config_exists: bool
    sample_bucket: str | None
    final_failure_type: str | None
    build_status: str | None
    validation_status: str | None
    source_manifest_path: str | None
    source_manifest_baseline_ref: str | None
    source_manifest_git_head: str | None
    source_manifest_stable_git_dir: str | None
    source_manifest_output_dir: str | None
    source_manifest_matches_request: bool
    source_provenance_status: str

    @property
    def complete(self) -> bool:
        return (
            self.status == "prepared"
            and self.stable_baseline_ready
            and self.source_manifest_exists
            and self.makefile_exists
            and self.setlocalversion_exists
            and self.config_exists
        )

    @property
    def git_source_traceable(self) -> bool:
        return (
            self.source_manifest_exists
            and self.source_manifest_matches_request
            and _looks_git_commit(self.source_manifest_git_head)
            and bool(self.source_manifest_stable_git_dir)
        )


def build_stable_baseline_evidence_manifest(
    evaluation_paths: Iterable[Path],
    *,
    output_json: Path,
    output_md: Path,
) -> dict[str, Any]:
    """Build a stable baseline evidence manifest from screening reports."""

    entries: list[StableBaselineEvidence] = []
    seen: set[tuple[str, str | None, str | None]] = set()
    for evaluation_path in evaluation_paths:
        payload = _read_json(evaluation_path)
        if not isinstance(payload, dict):
            continue
        for result in payload.get("results", []):
            if not isinstance(result, dict):
                continue
            evidence = _extract_evidence(result)
            if evidence is None:
                continue
            key = (evidence.cve_id, evidence.baseline_ref, evidence.output_dir)
            if key in seen:
                continue
            seen.add(key)
            entries.append(evidence)

    manifest = {
        "schema_version": 1,
        "total": len(entries),
        "prepared": sum(1 for item in entries if item.status == "prepared"),
        "complete": sum(1 for item in entries if item.complete),
        "incomplete": sum(1 for item in entries if not item.complete),
        "git_source_traceable": sum(1 for item in entries if item.git_source_traceable),
        "git_source_untraceable": sum(1 for item in entries if not item.git_source_traceable),
        "entries": [_entry_to_dict(item) for item in entries],
        "source_evaluation_paths": [str(path) for path in evaluation_paths],
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.write_text(render_stable_baseline_markdown(manifest), encoding="utf-8")
    return manifest


def render_stable_baseline_markdown(manifest: dict[str, Any]) -> str:
    """Render stable baseline evidence as a concise Markdown report."""

    lines = [
        "# PatchWeaver Stable Source Baseline Evidence",
        "",
        f"- Total entries: {manifest.get('total', 0)}",
        f"- Prepared: {manifest.get('prepared', 0)}",
        f"- Complete filesystem evidence: {manifest.get('complete', 0)}",
        f"- Incomplete: {manifest.get('incomplete', 0)}",
        f"- Git source traceable: {manifest.get('git_source_traceable', 0)}",
        f"- Git source untraceable: {manifest.get('git_source_untraceable', 0)}",
        "",
        "## Entries",
        "",
    ]
    for item in manifest.get("entries", []):
        lines.append(
            "- "
            f"{item.get('cve_id')}: "
            f"status=`{item.get('status')}`, "
            f"baseline_ref=`{item.get('baseline_ref') or 'unknown'}`, "
            f"ready=`{item.get('stable_baseline_ready')}`, "
            f"complete=`{item.get('complete')}`, "
            f"git_source=`{item.get('source_provenance_status') or 'unknown'}`, "
            f"failure=`{item.get('final_failure_type') or 'none'}`"
        )
        lines.append(f"  output_dir: `{item.get('output_dir') or 'unknown'}`")
    if not manifest.get("entries"):
        lines.append("- No stable baseline evidence found.")
    lines.extend(
        [
            "",
            "## Acceptance Meaning",
            "",
            "- `prepared` means `prepare-stable-baseline` completed and the full-run chain recorded the result.",
            "- `complete=true` means the prepared source tree has the required local evidence files: `Makefile`, `scripts/setlocalversion`, `.config`, and `patchweaver_stable_baseline.json`.",
            "- `git_source_traceable=true` additionally means the source manifest matches the requested baseline and records a git `HEAD` plus `stable_git_dir`; snapshot fallback remains useful but is reported separately.",
            "- This report proves source-state alignment, not final livepatch success. `.ko + load/unload/smoke/selftest` is still verified by the positive-pool evidence manifest.",
        ]
    )
    return "\n".join(lines) + "\n"


def _extract_evidence(result: dict[str, Any]) -> StableBaselineEvidence | None:
    preparation = result.get("stable_baseline_preparation")
    if not isinstance(preparation, dict):
        return None
    status = str(preparation.get("status") or "")
    output_dir = preparation.get("output_dir") or preparation.get("kernel_src_dir")
    output_path = Path(str(output_dir)) if output_dir else None
    baseline_ref = preparation.get("baseline_ref") or result.get("stable_source_baseline_ref")
    requested_baseline_ref = str(baseline_ref) if baseline_ref else None
    source_manifest_path = output_path / "patchweaver_stable_baseline.json" if output_path else None
    source_manifest_exists = bool(source_manifest_path and source_manifest_path.exists())
    source_manifest = _read_json(source_manifest_path) if source_manifest_path else {}
    if not isinstance(source_manifest, dict):
        source_manifest = {}
    source_manifest_baseline_ref = _string_or_none(source_manifest.get("baseline_ref"))
    source_manifest_git_head = _string_or_none(source_manifest.get("git_head"))
    source_manifest_stable_git_dir = _string_or_none(source_manifest.get("stable_git_dir"))
    source_manifest_output_dir = _string_or_none(source_manifest.get("output_dir"))
    source_manifest_matches_request = _source_manifest_matches_request(
        source_manifest,
        baseline_ref=requested_baseline_ref,
        output_dir=str(output_dir) if output_dir else None,
    )
    source_provenance_status = _source_provenance_status(
        output_dir=str(output_dir) if output_dir else None,
        source_manifest_exists=source_manifest_exists,
        source_manifest_matches_request=source_manifest_matches_request,
        git_head=source_manifest_git_head,
        stable_git_dir=source_manifest_stable_git_dir,
    )
    return StableBaselineEvidence(
        cve_id=str(result.get("cve_id") or "unknown"),
        baseline_ref=requested_baseline_ref,
        status=status,
        output_dir=str(output_dir) if output_dir else None,
        stable_baseline_ready=bool(result.get("stable_baseline_ready")),
        source_manifest_exists=source_manifest_exists,
        makefile_exists=_exists(output_path, "Makefile"),
        setlocalversion_exists=_exists(output_path, "scripts/setlocalversion"),
        config_exists=_exists(output_path, ".config"),
        sample_bucket=result.get("sample_bucket"),
        final_failure_type=result.get("failure_type") or result.get("run_failure_type"),
        build_status=result.get("build_status"),
        validation_status=result.get("validation_status"),
        source_manifest_path=str(source_manifest_path) if source_manifest_exists and source_manifest_path else None,
        source_manifest_baseline_ref=source_manifest_baseline_ref,
        source_manifest_git_head=source_manifest_git_head,
        source_manifest_stable_git_dir=source_manifest_stable_git_dir,
        source_manifest_output_dir=source_manifest_output_dir,
        source_manifest_matches_request=source_manifest_matches_request,
        source_provenance_status=source_provenance_status,
    )


def _exists(root: Path | None, relative: str) -> bool:
    if root is None:
        return False
    return (root / relative).exists()


def _entry_to_dict(item: StableBaselineEvidence) -> dict[str, Any]:
    payload = {
        "cve_id": item.cve_id,
        "baseline_ref": item.baseline_ref,
        "status": item.status,
        "output_dir": item.output_dir,
        "stable_baseline_ready": item.stable_baseline_ready,
        "source_manifest_exists": item.source_manifest_exists,
        "makefile_exists": item.makefile_exists,
        "setlocalversion_exists": item.setlocalversion_exists,
        "config_exists": item.config_exists,
        "sample_bucket": item.sample_bucket,
        "final_failure_type": item.final_failure_type,
        "build_status": item.build_status,
        "validation_status": item.validation_status,
        "complete": item.complete,
        "source_manifest_path": item.source_manifest_path,
        "source_manifest_baseline_ref": item.source_manifest_baseline_ref,
        "source_manifest_git_head": item.source_manifest_git_head,
        "source_manifest_stable_git_dir": item.source_manifest_stable_git_dir,
        "source_manifest_output_dir": item.source_manifest_output_dir,
        "source_manifest_matches_request": item.source_manifest_matches_request,
        "git_source_traceable": item.git_source_traceable,
        "source_provenance_status": item.source_provenance_status,
    }
    return payload


def _read_json(path: Path) -> Any:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _source_manifest_matches_request(
    payload: dict[str, Any],
    *,
    baseline_ref: str | None,
    output_dir: str | None,
) -> bool:
    if not payload:
        return False
    manifest_baseline_ref = _string_or_none(payload.get("baseline_ref"))
    if baseline_ref and manifest_baseline_ref != baseline_ref:
        return False
    manifest_output_dir = _string_or_none(payload.get("output_dir"))
    if output_dir and manifest_output_dir and _normalize_path_text(manifest_output_dir) != _normalize_path_text(output_dir):
        return False
    return manifest_baseline_ref is not None


def _source_provenance_status(
    *,
    output_dir: str | None,
    source_manifest_exists: bool,
    source_manifest_matches_request: bool,
    git_head: str | None,
    stable_git_dir: str | None,
) -> str:
    if not output_dir:
        return "no_output_dir"
    if not source_manifest_exists:
        return "source_manifest_missing"
    if not source_manifest_matches_request:
        return "source_manifest_mismatch"
    if _looks_git_commit(git_head) and stable_git_dir:
        return "git_worktree_traceable"
    if _looks_git_commit(git_head):
        return "git_head_without_stable_git_dir"
    return "snapshot_or_non_git_source"


def _looks_git_commit(value: str | None) -> bool:
    if value is None:
        return False
    return re.fullmatch(r"[0-9a-fA-F]{7,40}", value.strip()) is not None


def _normalize_path_text(value: str) -> str:
    return value.replace("\\", "/").rstrip("/")
