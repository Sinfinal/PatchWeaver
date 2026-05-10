"""Validate the Bailian/FC/MCP gateway against a reachable PatchWeaver API.

The script is safe by default: without ``--execute`` it only performs
gateway dry-runs.  Use ``--execute`` when the API base URL is reachable and
the selected actions are expected to be safe for the current environment.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from patchweaver.integrations.bailian_gateway import BailianGatewayConfig, BailianGatewayError, invoke_gateway


DEFAULT_ACTIONS = ("status", "agent_decision", "report", "replay")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base-url", default=os.getenv("PATCHWEAVER_API_BASE_URL", "http://127.0.0.1:18084/api/v1"))
    parser.add_argument("--task-id", default="", help="Existing task id for status/report/replay/agent_decision actions.")
    parser.add_argument("--cve-id", default="", help="CVE id used when action=create is requested.")
    parser.add_argument("--profile", default="demo", help="Profile used for create payload.")
    parser.add_argument("--target-kernel", default="", help="Optional target kernel used for create payload.")
    parser.add_argument("--max-attempts", type=int, default=1, help="Optional max attempts used for create payload.")
    parser.add_argument("--action", action="append", choices=("create", *DEFAULT_ACTIONS), help="Action to validate. Repeatable.")
    parser.add_argument("--execute", action="store_true", help="Actually call the PatchWeaver API through the gateway.")
    parser.add_argument("--timeout-sec", type=int, default=60)
    parser.add_argument("--output-json", type=Path, default=Path("data/evaluations/bailian_gateway_e2e.json"))
    parser.add_argument("--output-md", type=Path, default=Path("data/evaluations/bailian_gateway_e2e.md"))
    return parser.parse_args()


def payload_for_action(args: argparse.Namespace, action: str) -> dict[str, Any]:
    if action == "create":
        if not args.cve_id:
            raise SystemExit("--cve-id is required when action=create")
        payload: dict[str, Any] = {
            "cve_id": args.cve_id,
            "profile": args.profile,
            "max_attempts": args.max_attempts,
            "force_new": True,
        }
        if args.target_kernel:
            payload["target_kernel"] = args.target_kernel
        return payload
    if not args.task_id:
        raise SystemExit(f"--task-id is required when action={action}")
    return {"task_id": args.task_id}


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    actions = tuple(args.action or DEFAULT_ACTIONS)
    config = BailianGatewayConfig(
        api_key=os.getenv("PATCHWEAVER_BAILIAN_API_KEY"),
        api_base_url=args.api_base_url.rstrip("/"),
        timeout_seconds=max(args.timeout_sec, 1),
    )
    cases: list[dict[str, Any]] = []
    for action in actions:
        case: dict[str, Any] = {
            "action": action,
            "dry_run": not args.execute,
            "ok": False,
        }
        try:
            result = invoke_gateway(
                action,
                payload_for_action(args, action),
                dry_run=not args.execute,
                config=config,
            )
            case["ok"] = bool(result.get("ok"))
            case["request"] = result.get("request")
            case["response"] = result.get("response") if args.execute else None
        except (BailianGatewayError, OSError, ValueError) as exc:
            case["error"] = str(exc)
        cases.append(case)

    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "api_base_url": args.api_base_url.rstrip("/"),
        "mode": "execute" if args.execute else "dry_run",
        "task_id": args.task_id,
        "cve_id": args.cve_id,
        "actions": list(actions),
        "summary": {
            "total": len(cases),
            "ok": sum(1 for item in cases if item.get("ok")),
            "failed": sum(1 for item in cases if not item.get("ok")),
            "real_http_invoked": bool(args.execute),
            "secrets_written": False,
        },
        "cases": cases,
        "limits": [
            "dry_run mode validates the FC/MCP tool contract but does not prove livepatch build success.",
            "execute mode validates real gateway-to-API calls; .ko success still requires task artifact checks.",
            "Secret values are never written to this report.",
        ],
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# PatchWeaver Bailian / FC / MCP E2E Validation",
        "",
        f"- Mode: `{report['mode']}`",
        f"- API base URL: `{report['api_base_url']}`",
        f"- Task ID: `{report.get('task_id') or 'not set'}`",
        f"- CVE ID: `{report.get('cve_id') or 'not set'}`",
        f"- Actions: `{', '.join(report['actions'])}`",
        "",
        "## Summary",
        "",
        f"- Total: {report['summary']['total']}",
        f"- OK: {report['summary']['ok']}",
        f"- Failed: {report['summary']['failed']}",
        f"- Real HTTP invoked: `{report['summary']['real_http_invoked']}`",
        f"- Secrets written: `{report['summary']['secrets_written']}`",
        "",
        "## Cases",
        "",
        "| Action | Mode | OK | HTTP Status / Error |",
        "| --- | --- | --- | --- |",
    ]
    for item in report["cases"]:
        response = item.get("response") if isinstance(item.get("response"), dict) else {}
        status = response.get("status") or item.get("error") or "dry-run"
        lines.append(f"| `{item['action']}` | `{'execute' if not item['dry_run'] else 'dry_run'}` | `{item['ok']}` | `{status}` |")
    lines.extend(["", "## Limits", ""])
    for item in report["limits"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    report = build_report(args)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output_md.write_text(render_markdown(report), encoding="utf-8")
    print(f"bailian gateway e2e json written: {args.output_json}")
    print(f"bailian gateway e2e markdown written: {args.output_md}")
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
