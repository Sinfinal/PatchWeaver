"""CLI wrapper for the PatchWeaver Bailian gateway."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from patchweaver.integrations.bailian_gateway import (  # noqa: E402
    BailianGatewayError,
    invoke_gateway,
    openapi_schema,
    operation_schema,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PatchWeaver Bailian gateway CLI")
    parser.add_argument("--schema", action="store_true", help="Print FC/MCP JSON schema and exit.")
    parser.add_argument("--openapi", action="store_true", help="Print Bailian plugin OpenAPI schema and exit.")
    parser.add_argument(
        "--server-url",
        default="https://patchweaver-gateway.example.com",
        help="Server URL to place in the generated OpenAPI document.",
    )
    parser.add_argument(
        "--action",
        choices=("create", "status", "analyze", "run", "report", "replay", "agent_decision"),
        help="PatchWeaver operation to wrap.",
    )
    parser.add_argument("--payload-json", default="{}", help="JSON object payload for the selected action.")
    parser.add_argument("--invoke", action="store_true", help="Call PATCHWEAVER_API_BASE_URL instead of dry-run.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.schema:
        print(json.dumps(operation_schema(), ensure_ascii=False, indent=2))
        return 0
    if args.openapi:
        print(json.dumps(openapi_schema(args.server_url), ensure_ascii=False, indent=2))
        return 0

    if not args.action:
        print("--action is required unless --schema is used", file=sys.stderr)
        return 2

    try:
        payload: Any = json.loads(args.payload_json)
    except json.JSONDecodeError as exc:
        print(f"--payload-json must be valid JSON: {exc}", file=sys.stderr)
        return 2

    if not isinstance(payload, dict):
        print("--payload-json must decode to a JSON object", file=sys.stderr)
        return 2

    try:
        result = invoke_gateway(args.action, payload, dry_run=not args.invoke)
    except BailianGatewayError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
