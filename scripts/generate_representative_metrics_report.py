from __future__ import annotations

import argparse
from pathlib import Path

from patchweaver.reporter.representative_metrics import write_representative_metrics_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate representative holdout metrics report.")
    parser.add_argument("--holdout", required=True, type=Path)
    parser.add_argument("--evidence-manifest", type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--output-md", type=Path)
    parser.add_argument("--target-success-rate", type=float, default=0.60)
    args = parser.parse_args()

    report = write_representative_metrics_report(
        holdout_path=args.holdout,
        evidence_manifest_path=args.evidence_manifest,
        output_json_path=args.output_json,
        output_md_path=args.output_md,
        target_success_rate=args.target_success_rate,
    )
    print(f"representative metrics written: {args.output_json}")
    if args.output_md:
        print(f"representative metrics markdown written: {args.output_md}")
    print(f"representative_success_rate: {report['metrics']['representative_success_rate']:.2%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
