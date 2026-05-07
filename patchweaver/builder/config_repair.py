"""Minimal kernel config repair hints"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def infer_minimal_config_delta(*, source_dir: Path | None, target_files: list[Path]) -> dict[str, Any]:
    """Infer CONFIG entries needed to compile disabled target files"""

    if source_dir is None or not source_dir.exists():
        return {
            "status": "source_missing",
            "config_delta": {},
            "target_files": [path.as_posix() for path in target_files],
            "reason": "源码树不可用，无法推导 Kconfig 修复项",
        }

    findings: list[dict[str, Any]] = []
    config_delta: dict[str, str] = {}
    for relative_path in target_files:
        file_findings = _infer_file_config_keys(source_dir=source_dir, relative_path=relative_path)
        findings.extend(file_findings)
        for item in file_findings:
            key = str(item.get("config") or "")
            if key:
                config_delta[key] = "m"

    status = "repairable" if config_delta else "no_config_gate_found"
    reason = (
        "已找到可尝试打开的最小 CONFIG 集合"
        if config_delta
        else "未在 Kbuild/Makefile 中定位到明确 CONFIG 门控"
    )
    return {
        "status": status,
        "config_delta": dict(sorted(config_delta.items())),
        "target_files": [path.as_posix() for path in target_files],
        "findings": findings,
        "reason": reason,
    }


def render_config_fragment(config_delta: dict[str, str]) -> str:
    """Render CONFIG delta as a merge_config style fragment"""

    lines = [f"{key}={value}" for key, value in sorted(config_delta.items())]
    return "\n".join(lines) + ("\n" if lines else "")


def _infer_file_config_keys(*, source_dir: Path, relative_path: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    current_dir = Path()
    for part in relative_path.parent.parts:
        make_lines = _load_kbuild_lines(source_dir / current_dir)
        findings.extend(
            _find_directory_gate_configs(
                make_lines=make_lines,
                subdir_name=part,
                makefile_dir=current_dir,
            )
        )
        current_dir = current_dir / part

    make_lines = _load_kbuild_lines(source_dir / relative_path.parent)
    object_name = relative_path.with_suffix(".o").name
    composite_object = _find_composite_object(make_lines, member_object=object_name)
    final_object = composite_object or object_name
    findings.extend(
        _find_object_gate_configs(
            make_lines=make_lines,
            object_name=final_object,
            makefile_dir=relative_path.parent,
        )
    )
    return findings


def _load_kbuild_lines(directory: Path) -> list[str]:
    for candidate_name in ["Makefile", "Kbuild"]:
        candidate = directory / candidate_name
        if not candidate.exists():
            continue
        return _collapse_make_lines(candidate.read_text(encoding="utf-8", errors="replace"))
    return []


def _collapse_make_lines(content: str) -> list[str]:
    logical_lines: list[str] = []
    pending = ""
    for raw_line in content.splitlines():
        body, _, _ = raw_line.partition("#")
        stripped = body.rstrip()
        if not stripped:
            continue
        if stripped.endswith("\\"):
            pending += stripped[:-1].rstrip() + " "
            continue
        combined = (pending + stripped).strip()
        pending = ""
        if combined:
            logical_lines.append(combined)
    if pending.strip():
        logical_lines.append(pending.strip())
    return logical_lines


def _find_directory_gate_configs(*, make_lines: list[str], subdir_name: str, makefile_dir: Path) -> list[dict[str, Any]]:
    token = f"{subdir_name}/"
    return [
        {
            "type": "directory_gate",
            "config": config,
            "token": token,
            "makefile_dir": makefile_dir.as_posix() or ".",
            "line": line,
        }
        for line, config in _iter_obj_config_lines(make_lines)
        if token in line.split("=", 1)[-1].split()
    ]


def _find_object_gate_configs(*, make_lines: list[str], object_name: str, makefile_dir: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for line, config in _iter_obj_config_lines(make_lines):
        tokens = line.split("=", 1)[-1].split()
        if object_name not in tokens:
            continue
        findings.append(
            {
                "type": "object_gate",
                "config": config,
                "token": object_name,
                "makefile_dir": makefile_dir.as_posix() or ".",
                "line": line,
            }
        )
    return findings


def _iter_obj_config_lines(make_lines: list[str]) -> list[tuple[str, str]]:
    pattern = re.compile(r"^obj-\$\((CONFIG_[A-Za-z0-9_]+)\)\s*[:+]?=\s*(?P<rest>.+)$")
    matches: list[tuple[str, str]] = []
    for line in make_lines:
        match = pattern.match(line)
        if match:
            matches.append((line, match.group(1)))
    return matches


def _find_composite_object(make_lines: list[str], *, member_object: str) -> str | None:
    pattern = re.compile(r"^(?P<parent>[\w-]+)-(?:objs|y|m|\$\([^)]+\))\s*[:+]?=\s*(?P<rest>.+)$")
    for line in make_lines:
        match = pattern.match(line)
        if match is None:
            continue
        parent_name = match.group("parent")
        if parent_name in {"obj", "lib", "always", "extra", "subdir", "targets"}:
            continue
        if member_object in match.group("rest").split():
            return f"{parent_name}.o"
    return None
