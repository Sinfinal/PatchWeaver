"""Generate the P2 submission manifest and Markdown summary."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from patchweaver.reporter.submission_package import DEFAULT_BAILIAN_ENV_VARS, build_submission_package


DEFAULT_POSITIVE_EVIDENCE = Path("data/manifests/positive_pool_evidence_manifest.json")
DEFAULT_HOLDOUT_REPORT = Path("data/evaluations/p2_holdout_dry_run.json")
DEFAULT_DEMO_MANIFEST = Path("data/reports/demo_submission_manifest.json")
DEFAULT_OUTPUT_MANIFEST = Path("data/submission/submission_manifest.json")
DEFAULT_OUTPUT_MD = Path("data/submission/submission_summary.md")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positive-evidence", type=Path, default=DEFAULT_POSITIVE_EVIDENCE)
    parser.add_argument("--holdout-report", type=Path, default=DEFAULT_HOLDOUT_REPORT)
    parser.add_argument("--demo-manifest", type=Path, default=DEFAULT_DEMO_MANIFEST)
    parser.add_argument("--output-manifest", type=Path, default=DEFAULT_OUTPUT_MANIFEST)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--bailian-entrypoint", default="PLACEHOLDER_BAILIAN_ENTRYPOINT")
    parser.add_argument(
        "--bailian-env",
        action="append",
        dest="bailian_env",
        help="Required Bailian environment variable name. Repeat to add multiple names.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = build_submission_package(
        positive_evidence_path=args.positive_evidence,
        holdout_report_path=args.holdout_report,
        demo_manifest_path=args.demo_manifest,
        output_manifest_path=args.output_manifest,
        output_markdown_path=args.output_md,
        bailian_entrypoint=args.bailian_entrypoint,
        bailian_env_vars=tuple(args.bailian_env) if args.bailian_env else DEFAULT_BAILIAN_ENV_VARS,
    )
    print(f"submission manifest written: {manifest['artifacts']['submission_manifest_json']}")
    print(f"submission summary written: {manifest['artifacts']['submission_summary_md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
