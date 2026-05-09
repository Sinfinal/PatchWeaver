from __future__ import annotations

import argparse
from pathlib import Path

from patchweaver.reporter.demo_report import build_demo_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate PatchWeaver demo report and submission manifest.")
    parser.add_argument("--workspace-root", required=True, type=Path)
    parser.add_argument("--reports-root", required=True, type=Path)
    parser.add_argument("--positive-evidence", type=Path)
    parser.add_argument("--output-md", required=True, type=Path)
    parser.add_argument("--manifest-output", required=True, type=Path)
    args = parser.parse_args()

    manifest = build_demo_report(
        workspace_root=args.workspace_root,
        reports_root=args.reports_root,
        positive_evidence_path=args.positive_evidence,
        output_md=args.output_md,
        manifest_output=args.manifest_output,
    )
    print(f"demo report written: {manifest['artifacts']['demo_report_md']}")
    print(f"submission manifest written: {manifest['artifacts']['submission_manifest_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
