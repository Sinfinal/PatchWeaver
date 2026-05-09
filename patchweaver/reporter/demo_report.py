"""Generate demo report and submission manifest from local evidence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def build_demo_report(
    *,
    workspace_root: Path,
    reports_root: Path,
    positive_evidence_path: Path | None,
    output_md: Path,
    manifest_output: Path,
) -> dict[str, Any]:
    """Collect workspace reports, positive evidence, and write demo assets."""

    positive_evidence = _load_positive_evidence(positive_evidence_path)
    workspace_reports = _collect_workspace_reports(workspace_root)
    standalone_reports = _collect_standalone_reports(reports_root)
    agent_decision_summary = _agent_decision_counts(workspace_reports)
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "workspace_root": str(workspace_root),
            "reports_root": str(reports_root),
            "positive_evidence_path": str(positive_evidence_path) if positive_evidence_path else None,
        },
        "summary": {
            "positive_evidence_count": len(positive_evidence),
            "workspace_report_count": len(workspace_reports),
            "standalone_report_count": len(standalone_reports),
            "ko_artifact_count": sum(1 for item in positive_evidence if item.get("ko_path")),
            "repair_intent_count": agent_decision_summary["repair_intent_count"],
            "strategy_switch_count": agent_decision_summary["strategy_switch_count"],
            "failure_attribution_count": agent_decision_summary["failure_attribution_count"],
        },
        "agent_decision_summary": agent_decision_summary,
        "positive_evidence": positive_evidence,
        "workspace_reports": workspace_reports,
        "standalone_reports": standalone_reports,
        "artifacts": {
            "demo_report_md": str(output_md),
            "submission_manifest_json": str(manifest_output),
        },
        "limits": [
            "Generated from local evidence only.",
            "Validation-machine live kpatch-build/load/unload evidence is not produced by this script.",
        ],
    }
    output_md.parent.mkdir(parents=True, exist_ok=True)
    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(_render_markdown(manifest), encoding="utf-8")
    manifest_output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def _load_positive_evidence(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [_normalize_positive_evidence(item) for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("positive_evidence", "evidence", "cases", "items", "entries"):
            value = payload.get(key)
            if isinstance(value, list):
                return [_normalize_positive_evidence(item) for item in value if isinstance(item, dict)]
        return [_normalize_positive_evidence(payload)]
    return []


def _normalize_positive_evidence(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    if not normalized.get("ko_path") and normalized.get("module_path"):
        normalized["ko_path"] = normalized["module_path"]
    if not normalized.get("vermagic") and normalized.get("module_vermagic"):
        normalized["vermagic"] = normalized["module_vermagic"]
    return normalized


def _collect_workspace_reports(root: Path) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    reports: list[dict[str, Any]] = []
    for report_path in sorted(root.glob("*/reports/report.json")):
        payload = _read_json(report_path)
        task_dir = report_path.parents[1]
        reports.append(
            {
                "task_id": payload.get("task_id") or task_dir.name,
                "cve_id": payload.get("cve_id"),
                "status": payload.get("status"),
                "report_path": str(report_path),
                "validation_reports": [str(path) for path in sorted(task_dir.glob("attempts/*/artifacts/validation_report.json"))],
                "ko_artifacts": [str(path) for path in sorted(task_dir.glob("attempts/*/artifacts/*.ko"))],
                "agent_decision_summary": _workspace_agent_decision_summary(payload, task_dir),
            }
        )
    return reports


def _collect_standalone_reports(root: Path) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    return [
        {
            "name": path.name,
            "path": str(path),
            "status": _read_json(path).get("status"),
        }
        for path in sorted(root.glob("*.json"))
    ]


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _workspace_agent_decision_summary(report_payload: dict[str, Any], task_dir: Path) -> dict[str, Any]:
    raw_summary = report_payload.get("agent_decision_summary")
    if isinstance(raw_summary, dict):
        return _normalize_agent_decision_summary(raw_summary, task_dir)

    attempt_dir = _latest_attempt_dir(task_dir)
    repair_intent_path = _first_existing_path(
        task_dir / "analysis" / "repair_intent.json",
        attempt_dir / "artifacts" / "repair_intent.json" if attempt_dir else None,
    )
    rewrite_plan_path = _first_existing_path(attempt_dir / "rewrite" / "rewrite_plan.json" if attempt_dir else None)
    failure_record_path = _first_existing_path(attempt_dir / "logs" / "failure_record.json" if attempt_dir else None)
    repair_intent = _read_json(repair_intent_path) if repair_intent_path else {}
    rewrite_plan = _read_json(rewrite_plan_path) if rewrite_plan_path else {}
    failure_record = _read_json(failure_record_path) if failure_record_path else {}

    intent_strategy = _first_present(repair_intent, keys=("recommended_strategy", "repair_strategy", "strategy"))
    selected_recipe = _first_present(rewrite_plan, keys=("selected_recipe", "recipe", "recipe_name"))
    selected_strategy = _first_present(rewrite_plan, keys=("selected_strategy", "strategy", "route", "rewrite_strategy"))
    final_strategy = selected_strategy or selected_recipe or intent_strategy
    failure_type = _first_present(failure_record, keys=("failure_type", "expected_failure_type"))
    strategy_switched = bool(
        intent_strategy
        and final_strategy
        and str(intent_strategy) not in {str(final_strategy), str(selected_recipe)}
    )
    return {
        "repair_intent": {
            "present": bool(repair_intent),
            "recommended_strategy": intent_strategy,
            "root_cause": repair_intent.get("root_cause"),
        },
        "selected_recipe": selected_recipe,
        "selected_strategy": selected_strategy,
        "strategy": final_strategy,
        "strategy_switch": {
            "present": bool(intent_strategy or selected_recipe or selected_strategy),
            "switched": strategy_switched,
            "reason": _first_present(rewrite_plan, keys=("selection_reason", "strategy_reason", "reason")),
        },
        "failure_attribution": {
            "present": bool(failure_record or failure_type),
            "failure_type": failure_type,
            "summary": _first_present(failure_record, keys=("summary",)),
        },
        "source_paths": {
            "repair_intent": str(repair_intent_path) if repair_intent_path else None,
            "rewrite_plan": str(rewrite_plan_path) if rewrite_plan_path else None,
            "failure_record": str(failure_record_path) if failure_record_path else None,
        },
    }


def _normalize_agent_decision_summary(raw_summary: dict[str, Any], task_dir: Path) -> dict[str, Any]:
    repair_intent = raw_summary.get("repair_intent") if isinstance(raw_summary.get("repair_intent"), dict) else {}
    strategy_switch = raw_summary.get("strategy_switch") if isinstance(raw_summary.get("strategy_switch"), dict) else {}
    failure_attribution = raw_summary.get("failure_attribution") if isinstance(raw_summary.get("failure_attribution"), dict) else {}
    failure_record = raw_summary.get("failure_record") if isinstance(raw_summary.get("failure_record"), dict) else {}
    failure_type = raw_summary.get("failure_type") or failure_attribution.get("failure_type") or failure_record.get("failure_type")
    return {
        "repair_intent": {
            "present": bool(repair_intent),
            "recommended_strategy": repair_intent.get("recommended_strategy") or strategy_switch.get("repair_intent_strategy"),
            "root_cause": repair_intent.get("root_cause"),
        },
        "selected_recipe": raw_summary.get("selected_recipe") or strategy_switch.get("selected_recipe"),
        "selected_strategy": raw_summary.get("selected_strategy") or strategy_switch.get("selected_strategy"),
        "strategy": raw_summary.get("strategy") or strategy_switch.get("final_strategy"),
        "strategy_switch": {
            "present": bool(strategy_switch),
            "switched": bool(strategy_switch.get("switched")),
            "reason": strategy_switch.get("reason"),
        },
        "failure_attribution": {
            "present": bool(failure_type or failure_attribution or failure_record),
            "failure_type": failure_type,
            "summary": failure_attribution.get("summary") or failure_record.get("summary"),
        },
        "source_paths": raw_summary.get("source_paths") if isinstance(raw_summary.get("source_paths"), dict) else {
            "repair_intent": str(task_dir / "analysis" / "repair_intent.json"),
            "rewrite_plan": None,
            "failure_record": None,
        },
    }


def _agent_decision_counts(workspace_reports: list[dict[str, Any]]) -> dict[str, int]:
    summaries = [item.get("agent_decision_summary") for item in workspace_reports]
    return {
        "repair_intent_count": sum(1 for item in summaries if _has_repair_intent(item)),
        "strategy_switch_count": sum(1 for item in summaries if _has_strategy_switch(item)),
        "failure_attribution_count": sum(1 for item in summaries if _has_failure_attribution(item)),
    }


def _has_repair_intent(summary: Any) -> bool:
    repair_intent = summary.get("repair_intent") if isinstance(summary, dict) else None
    return bool(isinstance(repair_intent, dict) and repair_intent.get("present"))


def _has_strategy_switch(summary: Any) -> bool:
    strategy_switch = summary.get("strategy_switch") if isinstance(summary, dict) else None
    return bool(isinstance(strategy_switch, dict) and strategy_switch.get("switched"))


def _has_failure_attribution(summary: Any) -> bool:
    failure_attribution = summary.get("failure_attribution") if isinstance(summary, dict) else None
    return bool(isinstance(failure_attribution, dict) and failure_attribution.get("present"))


def _latest_attempt_dir(task_dir: Path) -> Path | None:
    attempt_dirs = [path for path in sorted((task_dir / "attempts").glob("*")) if path.is_dir()]
    return attempt_dirs[-1] if attempt_dirs else None


def _first_existing_path(*paths: Path | None) -> Path | None:
    for path in paths:
        if path is not None and path.exists():
            return path
    return None


def _first_present(*sources: dict[str, Any] | None, keys: tuple[str, ...]) -> Any | None:
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in keys:
            value = source.get(key)
            if value not in (None, "", [], {}):
                return value
    return None


def _render_markdown(manifest: dict[str, Any]) -> str:
    lines = [
        "# PatchWeaver Demo Report",
        "",
        f"Generated at: `{manifest['generated_at']}`",
        "",
        "## Summary",
        "",
        f"- Positive evidence cases: {manifest['summary']['positive_evidence_count']}",
        f"- Workspace reports: {manifest['summary']['workspace_report_count']}",
        f"- KO artifacts in positive evidence: {manifest['summary']['ko_artifact_count']}",
        "",
        "## Positive Evidence",
        "",
    ]
    if not manifest["positive_evidence"]:
        lines.append("- No positive evidence manifest was provided.")
    for item in manifest["positive_evidence"]:
        lines.append(
            f"- {item.get('cve_id', 'unknown')}: ko=`{item.get('ko_path', 'missing')}`, vermagic=`{item.get('vermagic', 'unknown')}`"
        )
    lines.extend(["", "## Workspace Reports", ""])
    if not manifest["workspace_reports"]:
        lines.append("- No workspace report.json files were found.")
    for item in manifest["workspace_reports"]:
        lines.append(
            f"- {item.get('task_id')}: {item.get('cve_id') or 'unknown CVE'} status=`{item.get('status') or 'unknown'}`"
        )
    lines.extend(["", "## Agent Decision Evidence", ""])
    lines.append(f"- RepairIntent count: {manifest['summary']['repair_intent_count']}")
    lines.append(f"- Strategy switch count: {manifest['summary']['strategy_switch_count']}")
    lines.append(f"- Failure attribution count: {manifest['summary']['failure_attribution_count']}")
    for item in manifest["workspace_reports"]:
        decision = item.get("agent_decision_summary") if isinstance(item.get("agent_decision_summary"), dict) else {}
        repair_intent = decision.get("repair_intent") if isinstance(decision.get("repair_intent"), dict) else {}
        failure_attribution = decision.get("failure_attribution") if isinstance(decision.get("failure_attribution"), dict) else {}
        lines.append(
            "- "
            f"{item.get('task_id')}: "
            f"repair_intent=`{bool(repair_intent.get('present'))}`, "
            f"strategy=`{decision.get('strategy') or 'unknown'}`, "
            f"failure=`{failure_attribution.get('failure_type') or 'none'}`"
        )
    lines.extend(["", "## Limits", ""])
    for item in manifest["limits"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"
