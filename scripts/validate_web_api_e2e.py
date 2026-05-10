"""Run a judge-facing Web/API evidence check for one existing task."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ENDPOINTS = (
    ("healthz", "GET", "/healthz"),
    ("task_detail", "GET", "/api/v1/tasks/{task_id}"),
    ("agent_decision", "GET", "/api/v1/tasks/{task_id}/agent-decision"),
    ("task_report", "GET", "/api/v1/reports/tasks/{task_id}"),
    ("replay", "GET", "/api/v1/tasks/{task_id}/replay"),
    ("artifacts", "GET", "/api/v1/tasks/{task_id}/artifacts"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:18084")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--timeout-sec", type=int, default=30)
    parser.add_argument("--output-json", type=Path, default=Path("data/evaluations/web_api_e2e.json"))
    parser.add_argument("--output-md", type=Path, default=Path("data/evaluations/web_api_e2e.md"))
    return parser.parse_args()


def fetch_json(url: str, timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            body = json.loads(raw) if raw else {}
            return {"ok": True, "status": response.status, "body": body}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {"ok": False, "status": exc.code, "error": body}
    except OSError as exc:
        return {"ok": False, "status": None, "error": str(exc)}


def _format_url(base_url: str, path: str, task_id: str) -> str:
    clean_base = base_url.rstrip("/")
    escaped_task = urllib.parse.quote(task_id, safe="")
    return f"{clean_base}{path.format(task_id=escaped_task)}"


def _find_module_path(task_detail: dict[str, Any], artifacts: dict[str, Any]) -> str | None:
    attempts = task_detail.get("attempts") if isinstance(task_detail.get("attempts"), list) else []
    for attempt in reversed(attempts):
        if isinstance(attempt, dict) and attempt.get("module_path"):
            return str(attempt["module_path"])
    artifact_items = artifacts.get("artifacts") or artifacts.get("items") or []
    if isinstance(artifact_items, list):
        for item in artifact_items:
            if isinstance(item, dict):
                path = str(item.get("path") or item.get("relative_path") or "")
                if path.endswith(".ko"):
                    return path
    return None


def _validation_status(task_detail: dict[str, Any], task_report: dict[str, Any]) -> str:
    for container in (task_detail, task_report):
        latest = container.get("latest_validation") if isinstance(container, dict) else None
        if isinstance(latest, dict):
            status = latest.get("status")
            if status:
                return str(status)
            matrix = latest.get("validation_matrix")
            if isinstance(matrix, dict) and matrix.get("status"):
                return str(matrix["status"])
    return "unknown"


def build_report(base_url: str, task_id: str, timeout: int) -> dict[str, Any]:
    endpoints: list[dict[str, Any]] = []
    bodies: dict[str, dict[str, Any]] = {}
    for name, method, path in ENDPOINTS:
        url = _format_url(base_url, path, task_id)
        result = fetch_json(url, timeout)
        endpoints.append({"name": name, "method": method, "url": url, **result})
        if result.get("ok") and isinstance(result.get("body"), dict):
            bodies[name] = result["body"]

    task_detail = bodies.get("task_detail", {})
    task_report = bodies.get("task_report", {})
    artifacts = bodies.get("artifacts", {})
    module_path = _find_module_path(task_detail, artifacts)
    validation_status = _validation_status(task_detail, task_report)
    report_ok = bool(task_report)
    replay_ok = bool(bodies.get("replay"))
    agent_decision_ok = bool(bodies.get("agent_decision"))
    success = bool(module_path) and validation_status == "passed" and report_ok and replay_ok
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url.rstrip("/"),
        "task_id": task_id,
        "summary": {
            "endpoint_total": len(endpoints),
            "endpoint_ok": sum(1 for item in endpoints if item.get("ok")),
            "endpoint_failed": sum(1 for item in endpoints if not item.get("ok")),
            "module_path": module_path,
            "validation_status": validation_status,
            "report_ok": report_ok,
            "replay_ok": replay_ok,
            "agent_decision_ok": agent_decision_ok,
            "judge_success_evidence": success,
        },
        "endpoints": endpoints,
        "limits": [
            "This check validates API evidence for an existing task; it does not rerun kpatch-build.",
            "Judge success still requires the referenced .ko and validation artifacts to be present on the validation machine.",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# PatchWeaver Web/API E2E Validation",
        "",
        f"- Base URL: `{report['base_url']}`",
        f"- Task ID: `{report['task_id']}`",
        f"- Endpoint OK: `{summary['endpoint_ok']}/{summary['endpoint_total']}`",
        f"- Module path: `{summary.get('module_path') or 'missing'}`",
        f"- Validation status: `{summary['validation_status']}`",
        f"- Report OK: `{summary['report_ok']}`",
        f"- Replay OK: `{summary['replay_ok']}`",
        f"- Agent decision OK: `{summary['agent_decision_ok']}`",
        f"- Judge success evidence: `{summary['judge_success_evidence']}`",
        "",
        "## Endpoints",
        "",
        "| Name | Method | OK | Status |",
        "| --- | --- | --- | --- |",
    ]
    for item in report["endpoints"]:
        lines.append(f"| `{item['name']}` | `{item['method']}` | `{item['ok']}` | `{item.get('status')}` |")
    lines.extend(["", "## Limits", ""])
    for item in report["limits"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    report = build_report(args.base_url, args.task_id, max(args.timeout_sec, 1))
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output_md.write_text(render_markdown(report), encoding="utf-8")
    print(f"web/api e2e json written: {args.output_json}")
    print(f"web/api e2e markdown written: {args.output_md}")
    return 0 if report["summary"]["endpoint_failed"] == 0 and report["summary"]["judge_success_evidence"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
