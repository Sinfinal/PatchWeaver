"""Build an evidence manifest for the confirmed positive CVE pool."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from patchweaver.reporter.positive_pool_manifest import write_positive_pool_evidence_manifest


DEFAULT_FIXTURE = Path("evaluations/fixtures/challenge_positive_pool_confirmed_v0426.json")
DEFAULT_WORKSPACE_ROOT = Path(".")
DEFAULT_OUTPUT = Path("data/manifests/positive_pool_evidence_manifest.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE, help="Positive pool fixture JSON path.")
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=DEFAULT_WORKSPACE_ROOT,
        help="Project root containing workspaces/ or the workspaces/ directory itself.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output manifest JSON path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = write_positive_pool_evidence_manifest(
        fixture_path=args.fixture,
        workspace_root=args.workspace_root,
        output_path=args.output,
    )
    print(output_path)


if __name__ == "__main__":
    main()
