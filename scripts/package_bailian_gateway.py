"""Package the PatchWeaver Bailian gateway for Aliyun Function Compute."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from patchweaver.integrations.bailian_fc_package import (
    build_bailian_fc_package,
    build_bailian_readiness_manifest,
    build_bailian_web_fc_package,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-zip", type=Path, default=Path("data/submission/bailian_gateway_fc_package.zip"))
    parser.add_argument("--manifest-output", type=Path, default=Path("data/submission/bailian_gateway_fc_package.json"))
    parser.add_argument(
        "--package-type",
        choices=("event", "web"),
        default="event",
        help="event builds index.handler; web builds a custom-runtime HTTP package for stable plugin URLs.",
    )
    parser.add_argument(
        "--readiness-output",
        type=Path,
        help="Optional non-secret production-readiness manifest for the deployed Bailian/FC gateway.",
    )
    parser.add_argument(
        "--public-url",
        default="",
        help="Public FC/API-Gateway base URL to record in the readiness manifest.",
    )
    parser.add_argument(
        "--mcp-service-id",
        default="",
        help="Optional Bailian MCP service id to record in the readiness manifest.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.package_type == "web":
        manifest = build_bailian_web_fc_package(output_zip=args.output_zip, manifest_output=args.manifest_output)
        print(f"bailian FC web package written: {manifest['package']}")
        print(f"startup_command: {manifest['startup_command']}")
        print(f"listen_port: {manifest['listen_port']}")
    else:
        manifest = build_bailian_fc_package(output_zip=args.output_zip, manifest_output=args.manifest_output)
        print(f"bailian FC package written: {manifest['package']}")
        print(f"entrypoint: {manifest['entrypoint']}")
    if args.readiness_output:
        if not args.public_url:
            print("--public-url is required when --readiness-output is set", file=sys.stderr)
            return 2
        readiness = build_bailian_readiness_manifest(
            output_path=args.readiness_output,
            public_url=args.public_url,
            mcp_service_id=args.mcp_service_id or None,
        )
        print(f"readiness manifest written: {args.readiness_output}")
        print(f"readiness status: {readiness['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
