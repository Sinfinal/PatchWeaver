"""Build a stable source baseline evidence manifest from screening reports."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from patchweaver.reporter.stable_baseline_evidence import build_stable_baseline_evidence_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evaluation", nargs="+", type=Path, help="Screening/evaluation JSON file.")
    parser.add_argument("--output-json", type=Path, default=Path("data/manifests/stable_baseline_evidence_manifest.json"))
    parser.add_argument("--output-md", type=Path, default=Path("data/manifests/stable_baseline_evidence_manifest.md"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = build_stable_baseline_evidence_manifest(
        args.evaluation,
        output_json=args.output_json,
        output_md=args.output_md,
    )
    print(
        "stable baseline evidence manifest written: "
        f"{args.output_json} total={manifest['total']} complete={manifest['complete']}"
    )
    print(f"stable baseline evidence report written: {args.output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

