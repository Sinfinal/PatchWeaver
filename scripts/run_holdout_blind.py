from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Final-style holdout blind metadata/dry-run summary.")
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mode", choices=["metadata", "dry-run"], default="metadata")
    parser.add_argument("--reveal-identities", action="store_true")
    args = parser.parse_args()

    fixture = _read_json(args.fixture)
    cases = _cases(fixture)
    case_summaries = [
        _case_summary(case, index=index, mode=args.mode, reveal=args.reveal_identities)
        for index, case in enumerate(cases, start=1)
    ]
    summary = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed",
        "mode": args.mode,
        "dry_run": True,
        "fixture_name": fixture.get("fixture_name") or fixture.get("name") or args.fixture.stem,
        "fixture_path": str(args.fixture),
        "total_cases": len(cases),
        "cases": case_summaries,
        "agent_decision_summary": _agent_decision_summary(case_summaries),
        "limits": [
            "No kpatch-build command is invoked.",
            "Blind identity is hidden unless --reveal-identities is passed.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"holdout summary written: {args.output}")
    return 0


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return {"cases": payload}
    return payload if isinstance(payload, dict) else {"cases": []}


def _cases(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("cases", "fixtures", "items", "holdout"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _case_summary(case: dict[str, Any], *, index: int, mode: str, reveal: bool) -> dict[str, Any]:
    identity = str(case.get("cve_id") or case.get("id") or index)
    agent_decision_surface = _agent_decision_surface(case)
    item = {
        "blind_id": f"HOLDOUT-{index:03d}-{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:8]}",
        "mode": mode,
        "bucket": case.get("bucket") or case.get("expected_bucket"),
        "metadata": {
            "target_kernel": case.get("target_kernel"),
            "expected_artifact_count": len(case.get("expected_artifacts") or []),
            "has_repair_intent": bool(case.get("repair_intent") or case.get("repair_intent_path")),
            "has_strategy_hint": agent_decision_surface["strategy_switch"]["present"],
            "has_failure_attribution": agent_decision_surface["failure_attribution"]["present"],
        },
        "agent_decision_surface": agent_decision_surface,
        "planned_actions": ["metadata_only"] if mode == "metadata" else ["load_fixture", "plan_attempt", "skip_kpatch_build"],
    }
    if reveal:
        item["cve_id"] = case.get("cve_id")
        item["source_id"] = case.get("id")
    return item


def _agent_decision_surface(case: dict[str, Any]) -> dict[str, Any]:
    repair_intent = case.get("repair_intent") if isinstance(case.get("repair_intent"), dict) else {}
    intent_strategy = _first_present(
        repair_intent,
        case,
        keys=("recommended_strategy", "repair_strategy", "strategy"),
    )
    selected_recipe = _first_present(case, keys=("selected_recipe", "recipe", "recipe_name"))
    selected_strategy = _first_present(case, keys=("selected_strategy", "rewrite_strategy", "route"))
    final_strategy = selected_strategy or selected_recipe or intent_strategy
    failure_type = _first_present(case, keys=("expected_failure_type", "failure_type"))
    failure_attribution = case.get("failure_attribution") if isinstance(case.get("failure_attribution"), dict) else {}
    failure_present = bool(failure_type or failure_attribution)
    strategy_present = bool(intent_strategy or selected_recipe or selected_strategy)
    strategy_switched = bool(
        intent_strategy
        and final_strategy
        and str(intent_strategy) not in {str(final_strategy), str(selected_recipe)}
    )
    return {
        "repair_intent": {
            "present": bool(repair_intent or case.get("repair_intent_path")),
        },
        "strategy_switch": {
            "present": strategy_present,
            "switched": strategy_switched,
        },
        "failure_attribution": {
            "present": failure_present,
        },
    }


def _agent_decision_summary(cases: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "repair_intent_cases": sum(1 for item in cases if item["agent_decision_surface"]["repair_intent"]["present"]),
        "strategy_switch_cases": sum(1 for item in cases if item["agent_decision_surface"]["strategy_switch"]["present"]),
        "failure_attribution_cases": sum(
            1 for item in cases if item["agent_decision_surface"]["failure_attribution"]["present"]
        ),
    }


def _first_present(*sources: dict[str, Any], keys: tuple[str, ...]) -> Any | None:
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in keys:
            value = source.get(key)
            if value not in (None, "", [], {}):
                return value
    return None


if __name__ == "__main__":
    raise SystemExit(main())
