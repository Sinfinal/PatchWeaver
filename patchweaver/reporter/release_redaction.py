"""Release redaction checks for secrets and delivery-only configuration."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

DEFAULT_REQUIRED_ENV_VARS = (
    "PATCHWEAVER_BAILIAN_API_KEY",
    "PATCHWEAVER_API_BASE_URL",
)

DEFAULT_SCAN_GLOBS = (
    "*.py",
    "*.md",
    "*.yaml",
    "*.yml",
    "*.json",
    "*.toml",
    "*.sh",
    "*.cmd",
)

DEFAULT_EXCLUDED_NAMES = {
    ".git",
    ".idea",
    ".pytest_tmp",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
}


@dataclass(frozen=True)
class SecretRule:
    """A line-oriented secret detector that reports metadata only."""

    name: str
    description: str
    pattern: re.Pattern[str]


@dataclass(frozen=True)
class SecretFinding:
    """A safe finding record with no secret value or matched excerpt."""

    rule: str
    description: str
    path: str
    line: int


SECRET_RULES = (
    SecretRule(
        name="api_key_assignment",
        description="Possible plaintext API key assignment",
        pattern=re.compile(r"(?i)\b(api[_-]?key|access[_-]?key|secret[_-]?key)\b\s*[:=]\s*['\"][^'\"\s]{12,}['\"]"),
    ),
    SecretRule(
        name="bearer_token",
        description="Possible bearer token literal",
        pattern=re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]{20,}"),
    ),
    SecretRule(
        name="platform_token_assignment",
        description="Possible platform token assignment",
        pattern=re.compile(r"(?i)\b(access[_-]?token|platform[_-]?token|refresh[_-]?token)\b\s*[:=]\s*['\"][^'\"\s]{12,}['\"]"),
    ),
    SecretRule(
        name="root_password",
        description="Possible root password literal",
        pattern=re.compile(r"(?i)\b(root[_-]?password|root\s+password|password)\b\s*[:=]\s*['\"][^'\"\s]{8,}['\"]"),
    ),
    SecretRule(
        name="cookie_literal",
        description="Possible private cookie literal",
        pattern=re.compile(r"(?i)\b(cookie|set-cookie)\b\s*[:=]\s*['\"][^'\"]{20,}['\"]"),
    ),
    SecretRule(
        name="dashscope_key",
        description="Possible DashScope/Bailian API key literal",
        pattern=re.compile(r"\bsk-[A-Za-z0-9][A-Za-z0-9_-]{16,}\b"),
    ),
)


def build_release_redaction_record(
    *,
    scan_roots: Iterable[Path],
    project_root: Path,
    required_env_vars: Iterable[str] = DEFAULT_REQUIRED_ENV_VARS,
    environ: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Build a safe release redaction record without exposing secret values."""

    env = environ if environ is not None else os.environ
    roots = tuple(Path(root).resolve() for root in scan_roots)
    findings = scan_secret_patterns(roots=roots, project_root=project_root)
    env_checks = [
        {
            "name": name,
            "present": bool(env.get(name)),
            "status": "present" if env.get(name) else "missing",
        }
        for name in required_env_vars
    ]
    missing_env = [item["name"] for item in env_checks if item["status"] == "missing"]
    status = "failed" if findings or missing_env else "passed"

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "scan_roots": [safe_relative_path(project_root, root) for root in roots],
        "required_env": env_checks,
        "summary": {
            "findings": len(findings),
            "missing_env": len(missing_env),
        },
        "findings": [
            {
                "rule": finding.rule,
                "description": finding.description,
                "path": finding.path,
                "line": finding.line,
            }
            for finding in findings
        ],
    }


def scan_secret_patterns(*, roots: Iterable[Path], project_root: Path) -> list[SecretFinding]:
    """Scan text files for common plaintext secret patterns."""

    findings: list[SecretFinding] = []
    for path in iter_scan_files(roots):
        try:
            for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
                for rule in SECRET_RULES:
                    if rule.pattern.search(line):
                        findings.append(
                            SecretFinding(
                                rule=rule.name,
                                description=rule.description,
                                path=safe_relative_path(project_root, path),
                                line=line_no,
                            )
                        )
        except OSError:
            continue
    return findings


def iter_scan_files(roots: Iterable[Path]) -> Iterable[Path]:
    """Yield candidate text files while skipping caches and generated folders."""

    seen: set[Path] = set()
    for root in roots:
        resolved_root = root.resolve()
        candidates = [resolved_root] if resolved_root.is_file() else _glob_files(resolved_root)
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved in seen or should_exclude(resolved, root=resolved_root):
                continue
            seen.add(resolved)
            yield resolved


def _glob_files(root: Path) -> list[Path]:
    files: list[Path] = []
    if not root.exists():
        return files
    for pattern in DEFAULT_SCAN_GLOBS:
        files.extend(path for path in root.rglob(pattern) if path.is_file())
    return files


def should_exclude(path: Path, *, root: Path) -> bool:
    """Keep scans focused on source and docs instead of caches or binaries."""

    try:
        relative_parts = path.resolve().relative_to(root.resolve()).parts
    except ValueError:
        relative_parts = path.parts
    lowered = tuple(part.lower() for part in relative_parts)
    if any(part in DEFAULT_EXCLUDED_NAMES for part in lowered):
        return True
    return len(lowered) >= 2 and lowered[0] == "data" and lowered[1] == "cache"


def safe_relative_path(project_root: Path, path: Path) -> str:
    """Render stable paths without embedding local secret values."""

    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def write_release_redaction_record(record: dict[str, object], output_path: Path) -> None:
    """Persist the safe JSON record."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
