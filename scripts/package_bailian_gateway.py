"""Package the PatchWeaver Bailian gateway for Aliyun Function Compute."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from patchweaver.integrations.bailian_fc_package import build_bailian_fc_package


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-zip", type=Path, default=Path("data/submission/bailian_gateway_fc_package.zip"))
    parser.add_argument("--manifest-output", type=Path, default=Path("data/submission/bailian_gateway_fc_package.json"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = build_bailian_fc_package(output_zip=args.output_zip, manifest_output=args.manifest_output)
    print(f"bailian FC package written: {manifest['package']}")
    print(f"entrypoint: {manifest['entrypoint']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

