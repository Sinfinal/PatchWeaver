"""Run the Slice 7 release redaction and secret hygiene check."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from patchweaver.reporter.release_redaction import (  # noqa: E402
    DEFAULT_REQUIRED_ENV_VARS,
    build_release_redaction_record,
    write_release_redaction_record,
)

DEFAULT_OUTPUT = Path("data/submission/release_redaction_check.json")


def default_scan_roots(project_root: Path = PROJECT_ROOT) -> tuple[Path, ...]:
    """Return the source and delivery docs that must stay secret-free."""

    return (
        project_root / "README.md",
        project_root / "config",
        project_root / "docs",
        project_root / "submission" / "docs",
        project_root / "patchweaver",
        project_root / "scripts",
        project_root / "tests",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scan-root",
        action="append",
        type=Path,
        dest="scan_roots",
        help="Source or docs root to scan. Repeat to scan multiple roots.",
    )
    parser.add_argument(
        "--required-env",
        action="append",
        dest="required_env",
        help="Required environment variable name. Values are never printed.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    scan_roots = tuple(args.scan_roots) if args.scan_roots else default_scan_roots()
    required_env = tuple(args.required_env) if args.required_env else DEFAULT_REQUIRED_ENV_VARS
    output_path = args.output if args.output.is_absolute() else PROJECT_ROOT / args.output

    record = build_release_redaction_record(
        scan_roots=scan_roots,
        project_root=PROJECT_ROOT,
        required_env_vars=required_env,
    )
    write_release_redaction_record(record, output_path)

    print(f"release redaction status: {record['status']}")
    print(f"missing required env count: {record['summary']['missing_env']}")
    print(f"secret finding count: {record['summary']['findings']}")
    print(f"record written: {output_path}")
    return 0 if record["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
