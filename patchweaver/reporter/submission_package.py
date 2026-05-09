"""Submission package manifest and Markdown summary builder."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_BAILIAN_ENV_VARS = (
    "PATCHWEAVER_BAILIAN_API_KEY",
    "PATCHWEAVER_API_BASE_URL",
    "PATCHWEAVER_API_TIMEOUT_SECONDS",
)


def build_submission_package(
    *,
    positive_evidence_path: Path,
    holdout_report_path: Path,
    demo_manifest_path: Path,
    output_manifest_path: Path,
    output_markdown_path: Path,
    bailian_entrypoint: str = "PLACEHOLDER_BAILIAN_ENTRYPOINT",
    bailian_env_vars: tuple[str, ...] = DEFAULT_BAILIAN_ENV_VARS,
    include_generated_at: bool = True,
) -> dict[str, Any]:
    """Build and write a P2 submission manifest plus human-readable summary."""

    positive_evidence = _read_json(positive_evidence_path)
    holdout_report = _read_json(holdout_report_path)
    demo_manifest = _read_json(demo_manifest_path)

    confirmed_pool = _confirmed_pool_summary(positive_evidence)
    holdout_summary = _holdout_summary(holdout_report)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "inputs": {
            "positive_evidence_manifest": str(positive_evidence_path),
            "holdout_report": str(holdout_report_path),
            "demo_manifest": str(demo_manifest_path),
        },
        "artifacts": {
            "submission_manifest_json": str(output_manifest_path),
            "submission_summary_md": str(output_markdown_path),
        },
        "confirmed_pool": confirmed_pool,
        "representative_metrics": _representative_metrics(
            confirmed_pool=confirmed_pool,
            positive_evidence=positive_evidence,
            demo_manifest=demo_manifest,
        ),
        "p2_holdout": holdout_summary,
        "agent_decision_evidence": _agent_decision_evidence(
            demo_manifest=demo_manifest,
            holdout_summary=holdout_summary,
        ),
        "bailian_entrypoint": {
            "status": "placeholder",
            "value": bailian_entrypoint,
            "required_environment": [
                {"name": name, "required": True, "secret": name.endswith(("KEY", "TOKEN", "SECRET"))}
                for name in bailian_env_vars
            ],
            "secret_policy": "Environment variable names only; secret values are not read or written.",
        },
        "limits": [
            "Generated from local manifests and dry-run reports only.",
            "Does not contact the validation machine.",
            "Does not read, print, or write secret values.",
        ],
    }
    if include_generated_at:
        manifest["generated_at"] = datetime.now(timezone.utc).isoformat()

    output_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    output_markdown_path.parent.mkdir(parents=True, exist_ok=True)
    output_manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_markdown_path.write_text(render_submission_markdown(manifest), encoding="utf-8")
    return manifest


def render_submission_markdown(manifest: dict[str, Any]) -> str:
    """Render the submission manifest as a concise Markdown summary."""

    confirmed_pool = manifest["confirmed_pool"]
    metrics = manifest["representative_metrics"]
    holdout = manifest["p2_holdout"]
    agent_decision = manifest.get("agent_decision_evidence") or {}
    bailian = manifest["bailian_entrypoint"]

    lines = [
        "# PatchWeaver P2 Submission Summary",
        "",
        f"Generated at: `{manifest.get('generated_at', 'not recorded')}`",
        "",
        "## Confirmed Pool",
        "",
        f"- Total cases: {confirmed_pool['total']}",
        f"- Complete: {confirmed_pool['complete']}",
        f"- Partial: {confirmed_pool['partial']}",
        f"- Missing: {confirmed_pool['missing']}",
        "",
    ]
    if not confirmed_pool["entries"]:
        lines.append("- No confirmed pool entries were found.")
    for item in confirmed_pool["entries"]:
        lines.append(
            "- "
            f"{item.get('cve_id', 'unknown')}: "
            f"status=`{item.get('status', 'unknown')}`, "
            f"validation=`{item.get('validation_status') or 'unknown'}`, "
            f"module=`{item.get('module_path') or 'missing'}`"
        )

    lines.extend(
        [
            "",
            "## Representative Metrics",
            "",
            f"- Positive evidence completion rate: {metrics['positive_evidence_completion_rate']:.2%}",
            f"- KO artifact count: {metrics['ko_artifact_count']}",
            f"- Workspace report count: {metrics['workspace_report_count']}",
            f"- Standalone report count: {metrics['standalone_report_count']}",
            "",
            "## P2 Holdout",
            "",
            f"- Status: `{holdout['status']}`",
            f"- Mode: `{holdout['mode']}`",
            f"- Dry run: `{holdout['dry_run']}`",
            f"- Total cases: {holdout['total_cases']}",
            f"- Blind identities preserved: `{holdout['blind_identities_preserved']}`",
            "",
            "## Agent Decision Evidence",
            "",
            f"- RepairIntent count: {agent_decision.get('demo', {}).get('repair_intent_count', 0)}",
            f"- Strategy switch count: {agent_decision.get('demo', {}).get('strategy_switch_count', 0)}",
            f"- Failure attribution count: {agent_decision.get('demo', {}).get('failure_attribution_count', 0)}",
            f"- Holdout RepairIntent cases: {agent_decision.get('holdout', {}).get('repair_intent_cases', 0)}",
            f"- Holdout strategy switch cases: {agent_decision.get('holdout', {}).get('strategy_switch_cases', 0)}",
            f"- Holdout failure attribution cases: {agent_decision.get('holdout', {}).get('failure_attribution_cases', 0)}",
            "",
            "## Bailian Entrypoint",
            "",
            f"- Entrypoint placeholder: `{bailian['value']}`",
            f"- Status: `{bailian['status']}`",
            f"- Secret policy: {bailian['secret_policy']}",
        ]
    )
    for item in bailian["required_environment"]:
        secret_note = ", secret" if item["secret"] else ""
        lines.append(f"- Required env: `{item['name']}`{secret_note}")

    lines.extend(["", "## Limits", ""])
    for item in manifest["limits"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def _confirmed_pool_summary(payload: Any) -> dict[str, Any]:
    entries = _positive_entries(payload)
    normalized = [_normalize_positive_entry(item) for item in entries]
    total = _int_from_payload(payload, "total", len(normalized))
    complete = _int_from_payload(payload, "complete", sum(1 for item in normalized if item["status"] == "complete"))
    partial = _int_from_payload(payload, "partial", sum(1 for item in normalized if item["status"] == "partial"))
    missing = _int_from_payload(payload, "missing", sum(1 for item in normalized if item["status"] == "missing"))
    return {
        "total": total,
        "complete": complete,
        "partial": partial,
        "missing": missing,
        "entries": normalized,
    }


def _representative_metrics(
    *,
    confirmed_pool: dict[str, Any],
    positive_evidence: Any,
    demo_manifest: Any,
) -> dict[str, Any]:
    demo_summary = demo_manifest.get("summary", {}) if isinstance(demo_manifest, dict) else {}
    total = max(int(confirmed_pool["total"]), 0)
    complete = max(int(confirmed_pool["complete"]), 0)
    return {
        "positive_evidence_completion_rate": (complete / total) if total else 0.0,
        "positive_manifest_complete": complete,
        "positive_manifest_partial": int(confirmed_pool["partial"]),
        "positive_manifest_missing": int(confirmed_pool["missing"]),
        "ko_artifact_count": _metric_from_demo_or_entries(
            demo_summary,
            confirmed_pool["entries"],
            "ko_artifact_count",
            lambda item: bool(item.get("module_path")),
        ),
        "repair_intent_count": int(demo_summary.get("repair_intent_count") or 0),
        "strategy_switch_count": int(demo_summary.get("strategy_switch_count") or 0),
        "failure_attribution_count": int(demo_summary.get("failure_attribution_count") or 0),
        "workspace_report_count": int(demo_summary.get("workspace_report_count") or 0),
        "standalone_report_count": int(demo_summary.get("standalone_report_count") or 0),
        "demo_positive_evidence_count": int(demo_summary.get("positive_evidence_count") or 0),
        "positive_manifest_source_total": _int_from_payload(positive_evidence, "total", len(confirmed_pool["entries"])),
    }


def _holdout_summary(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "status": "missing",
            "mode": "unknown",
            "dry_run": None,
            "total_cases": 0,
            "fixture_name": None,
            "cases": [],
            "blind_identities_preserved": False,
            "agent_decision_summary": {
                "repair_intent_cases": 0,
                "strategy_switch_cases": 0,
                "failure_attribution_cases": 0,
            },
            "limits": [],
        }
    cases = [item for item in payload.get("cases", []) if isinstance(item, dict)]
    agent_decision_summary = _holdout_agent_decision_summary(payload, cases)
    return {
        "status": str(payload.get("status") or "unknown"),
        "mode": str(payload.get("mode") or "unknown"),
        "dry_run": payload.get("dry_run"),
        "total_cases": int(payload.get("total_cases") or len(cases)),
        "fixture_name": payload.get("fixture_name"),
        "cases": [
            {
                "blind_id": item.get("blind_id"),
                "mode": item.get("mode"),
                "bucket": item.get("bucket"),
                "planned_actions": item.get("planned_actions") or [],
                "agent_decision_surface": item.get("agent_decision_surface") if isinstance(item.get("agent_decision_surface"), dict) else {},
            }
            for item in cases
        ],
        "blind_identities_preserved": all("cve_id" not in item and "source_id" not in item for item in cases),
        "agent_decision_summary": agent_decision_summary,
        "limits": payload.get("limits") if isinstance(payload.get("limits"), list) else [],
    }


def _agent_decision_evidence(*, demo_manifest: Any, holdout_summary: dict[str, Any]) -> dict[str, Any]:
    demo_summary = demo_manifest.get("summary", {}) if isinstance(demo_manifest, dict) else {}
    holdout_decision = holdout_summary.get("agent_decision_summary")
    if not isinstance(holdout_decision, dict):
        holdout_decision = {
            "repair_intent_cases": 0,
            "strategy_switch_cases": 0,
            "failure_attribution_cases": 0,
        }
    return {
        "demo": {
            "repair_intent_count": int(demo_summary.get("repair_intent_count") or 0),
            "strategy_switch_count": int(demo_summary.get("strategy_switch_count") or 0),
            "failure_attribution_count": int(demo_summary.get("failure_attribution_count") or 0),
        },
        "holdout": {
            "repair_intent_cases": int(holdout_decision.get("repair_intent_cases") or 0),
            "strategy_switch_cases": int(holdout_decision.get("strategy_switch_cases") or 0),
            "failure_attribution_cases": int(holdout_decision.get("failure_attribution_cases") or 0),
        },
        "ready_for_demo": bool(
            int(demo_summary.get("repair_intent_count") or 0)
            and int(demo_summary.get("failure_attribution_count") or 0)
        ),
    }


def _holdout_agent_decision_summary(payload: dict[str, Any], cases: list[dict[str, Any]]) -> dict[str, int]:
    raw_summary = payload.get("agent_decision_summary")
    if isinstance(raw_summary, dict):
        return {
            "repair_intent_cases": int(raw_summary.get("repair_intent_cases") or 0),
            "strategy_switch_cases": int(raw_summary.get("strategy_switch_cases") or 0),
            "failure_attribution_cases": int(raw_summary.get("failure_attribution_cases") or 0),
        }
    return {
        "repair_intent_cases": sum(1 for item in cases if _surface_present(item, "repair_intent")),
        "strategy_switch_cases": sum(1 for item in cases if _surface_present(item, "strategy_switch")),
        "failure_attribution_cases": sum(1 for item in cases if _surface_present(item, "failure_attribution")),
    }


def _surface_present(item: dict[str, Any], key: str) -> bool:
    surface = item.get("agent_decision_surface") if isinstance(item.get("agent_decision_surface"), dict) else {}
    value = surface.get(key) if isinstance(surface.get(key), dict) else {}
    return bool(value.get("present"))


def _positive_entries(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("entries", "positive_evidence", "evidence", "cases", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _normalize_positive_entry(item: dict[str, Any]) -> dict[str, Any]:
    evidence_paths = item.get("evidence_paths") if isinstance(item.get("evidence_paths"), dict) else {}
    module_path = item.get("module_path") or item.get("ko_path") or _first_path(evidence_paths.get("patchweaver-*.ko"))
    return {
        "cve_id": str(item.get("cve_id") or item.get("id") or "unknown"),
        "status": str(item.get("status") or "unknown"),
        "validation_status": item.get("validation_status") or item.get("validation"),
        "module_path": module_path,
        "module_vermagic": item.get("module_vermagic") or item.get("vermagic"),
        "missing_artifacts": item.get("missing_artifacts") if isinstance(item.get("missing_artifacts"), list) else [],
    }


def _metric_from_demo_or_entries(
    demo_summary: dict[str, Any],
    entries: list[dict[str, Any]],
    key: str,
    predicate: Any,
) -> int:
    if key in demo_summary:
        return int(demo_summary.get(key) or 0)
    return sum(1 for item in entries if predicate(item))


def _int_from_payload(payload: Any, key: str, default: int) -> int:
    if isinstance(payload, dict) and key in payload:
        try:
            return int(payload[key])
        except (TypeError, ValueError):
            return default
    return default


def _first_path(value: Any) -> str | None:
    if isinstance(value, list) and value:
        return str(value[0])
    if isinstance(value, str):
        return value
    return None


def _read_json(path: Path) -> Any:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
