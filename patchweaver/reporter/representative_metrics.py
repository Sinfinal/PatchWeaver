"""Representative holdout metrics report builder."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EVIDENCE_RESULT_KEYS = {
    "load": "load_result",
    "unload": "unload_result",
    "smoke": "smoke_result",
    "selftest": "selftest_result",
}


def build_representative_metrics_report(
    *,
    holdout_path: Path,
    evidence_manifest_path: Path | None = None,
    target_success_rate: float = 0.60,
    include_generated_at: bool = True,
) -> dict[str, Any]:
    """Build a reusable metrics report from a holdout run and optional evidence manifest."""

    holdout = _load_json_object(holdout_path)
    results = _as_list(holdout.get("results"))
    manifest_entries = _manifest_entries_by_cve(evidence_manifest_path)
    cases = [_build_case(result, manifest_entries.get(str(result.get("cve_id")))) for result in results]
    representative_total = int(holdout.get("summary", {}).get("representative_total") or len(cases))
    success_count = sum(1 for case in cases if case["success"])
    success_rate = _safe_ratio(success_count, representative_total)
    average_attempts = _average([case["attempt_count"] for case in cases])
    success_gap = max(0.0, round(target_success_rate - success_rate, 4))
    report: dict[str, Any] = {
        "source": {
            "holdout_path": str(holdout_path),
            "evidence_manifest_path": str(evidence_manifest_path) if evidence_manifest_path else None,
        },
        "metrics": {
            "representative_total": representative_total,
            "representative_success_count": success_count,
            "representative_success_rate": success_rate,
            "average_attempts": average_attempts,
            "success_gap_to_60_percent": success_gap,
            "target_success_rate": target_success_rate,
        },
        "evidence_summary": _build_evidence_summary(cases),
        "failure_buckets": _build_failure_buckets(cases),
        "model_rag_summary": _build_model_rag_summary(cases, holdout.get("summary", {})),
        "target_gap": _target_gap_explanation(
            success_count=success_count,
            representative_total=representative_total,
            success_rate=success_rate,
            target_success_rate=target_success_rate,
            average_attempts=average_attempts,
        ),
        "cases": cases,
    }
    if include_generated_at:
        report["generated_at"] = datetime.now(timezone.utc).isoformat()
    return report


def write_representative_metrics_report(
    *,
    holdout_path: Path,
    evidence_manifest_path: Path | None,
    output_json_path: Path,
    output_md_path: Path | None = None,
    target_success_rate: float = 0.60,
) -> dict[str, Any]:
    """Build and write representative metrics as JSON and optional Markdown."""

    report = build_representative_metrics_report(
        holdout_path=holdout_path,
        evidence_manifest_path=evidence_manifest_path,
        target_success_rate=target_success_rate,
    )
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md_path is not None:
        output_md_path.parent.mkdir(parents=True, exist_ok=True)
        output_md_path.write_text(render_representative_metrics_markdown(report), encoding="utf-8")
    return report


def render_representative_metrics_markdown(report: dict[str, Any]) -> str:
    """Render the representative metrics report in a compact delivery-friendly format."""

    metrics = report["metrics"]
    gap = report["target_gap"]
    evidence = report["evidence_summary"]
    lines = [
        "# Representative Holdout Metrics",
        "",
        "## Metrics",
        f"- representative_total: {metrics['representative_total']}",
        f"- representative_success_rate: {metrics['representative_success_rate']:.2%}",
        f"- average_attempts: {metrics['average_attempts']}",
        f"- target_success_rate: {metrics['target_success_rate']:.0%}",
        f"- success_gap_to_60_percent: {metrics['success_gap_to_60_percent']:.2%}",
        "",
        "## .ko/load/unload/smoke/selftest Evidence",
    ]
    for key in ("ko", "load", "unload", "smoke", "selftest"):
        item = evidence[key]
        lines.append(f"- {key}: present={item['present']} passed={item['passed']} total={item['total']}")
    lines.extend(["", "## Failure Buckets"])
    for bucket, count in report["failure_buckets"].items():
        lines.append(f"- {bucket}: {count}")
    lines.extend(["", "## Model/RAG Participation"])
    model_rag = report["model_rag_summary"]
    lines.append(f"- rag_seed_hits: {model_rag['rag_seed_hits']}")
    lines.append(f"- rag_subsystem_counts: {model_rag['rag_subsystem_counts']}")
    lines.append(f"- selected_route_counts: {model_rag['selected_route_counts']}")
    lines.append(f"- model_counts: {model_rag['model_counts']}")
    lines.append(f"- model_missing: {model_rag['model_missing']}")
    lines.extend(
        [
            "",
            "## Target Gap",
            f"- status: {gap['status']}",
            f"- explanation: {gap['explanation']}",
            "",
            "## Cases",
        ]
    )
    for case in report["cases"]:
        lines.append(
            "- "
            f"{case['cve_id']}: success={case['success']} attempts={case['attempt_count']} "
            f"bucket={case['failure_bucket']} route={case['model_rag']['selected_route']} "
            f"rag={case['model_rag']['rag_seed_hit']} "
            f"ko={case['evidence']['ko']['path']} load={case['evidence']['load']['status']} "
            f"unload={case['evidence']['unload']['status']} smoke={case['evidence']['smoke']['status']} "
            f"selftest={case['evidence']['selftest']['status']}"
        )
    return "\n".join(lines) + "\n"


def _build_case(result: dict[str, Any], manifest_entry: dict[str, Any] | None) -> dict[str, Any]:
    validation_report = result.get("validation_report") if isinstance(result.get("validation_report"), dict) else {}
    success = _is_success(result, manifest_entry)
    evidence = {
        "ko": _ko_evidence(result, manifest_entry),
        "load": _validation_evidence(validation_report, "load"),
        "unload": _validation_evidence(validation_report, "unload"),
        "smoke": _validation_evidence(validation_report, "smoke"),
        "selftest": _validation_evidence(validation_report, "selftest"),
    }
    return {
        "cve_id": str(result.get("cve_id") or "unknown"),
        "task_id": result.get("task_id"),
        "success": success,
        "run_status": result.get("run_status") or result.get("build_status"),
        "validation_status": result.get("validation_status"),
        "attempt_count": _attempt_count(result),
        "failure_bucket": _failure_bucket(result, success),
        "sample_bucket": result.get("sample_bucket"),
        "model_rag": _model_rag(result),
        "evidence": evidence,
        "evidence_paths": _evidence_paths(result, manifest_entry),
        "manifest_status": manifest_entry.get("status") if manifest_entry else None,
    }


def _is_success(result: dict[str, Any], manifest_entry: dict[str, Any] | None) -> bool:
    if result.get("run_status") == "built" and result.get("validation_status") == "passed":
        return True
    if result.get("build_status") == "built" and result.get("validation_status") == "passed":
        return True
    return bool(manifest_entry and manifest_entry.get("status") == "complete" and manifest_entry.get("validation_status") == "passed")


def _attempt_count(result: dict[str, Any]) -> int:
    attempts = _as_list(result.get("run_attempts"))
    if attempts:
        return len(attempts)
    value = result.get("run_index")
    return int(value) if isinstance(value, int) and value > 0 else 1


def _ko_evidence(result: dict[str, Any], manifest_entry: dict[str, Any] | None) -> dict[str, Any]:
    manifest_paths = (manifest_entry or {}).get("evidence_paths") if manifest_entry else None
    ko_paths = manifest_paths.get("patchweaver-*.ko") if isinstance(manifest_paths, dict) else None
    path = result.get("module_path") or (manifest_entry or {}).get("module_path") or _first_path(ko_paths)
    return {
        "present": bool(path),
        "status": "present" if path else "missing",
        "path": path,
        "vermagic": result.get("module_vermagic") or (manifest_entry or {}).get("module_vermagic"),
    }


def _validation_evidence(validation_report: dict[str, Any], name: str) -> dict[str, Any]:
    payload = validation_report.get(EVIDENCE_RESULT_KEYS[name])
    payload = payload if isinstance(payload, dict) else {}
    return {
        "present": bool(payload),
        "status": payload.get("status"),
        "path": payload.get("log_path"),
        "detail": payload.get("detail"),
        "command": payload.get("command"),
    }


def _build_evidence_summary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in ("ko", "load", "unload", "smoke", "selftest"):
        entries = [case["evidence"][key] for case in cases]
        summary[key] = {
            "present": sum(1 for entry in entries if entry.get("present") or entry.get("path")),
            "passed": sum(1 for entry in entries if entry.get("status") in {"passed", "present"}),
            "total": len(entries),
        }
    return summary


def _build_failure_buckets(cases: list[dict[str, Any]]) -> dict[str, int]:
    buckets: dict[str, int] = {}
    for case in cases:
        bucket = str(case.get("failure_bucket") or "unknown")
        buckets[bucket] = buckets.get(bucket, 0) + 1
    return buckets


def _build_model_rag_summary(cases: list[dict[str, Any]], holdout_summary: Any) -> dict[str, Any]:
    summary = holdout_summary if isinstance(holdout_summary, dict) else {}
    model_counts = _count_values(case["model_rag"].get("model_name") for case in cases)
    return {
        "rag_seed_hits": sum(1 for case in cases if case["model_rag"].get("rag_seed_hit") is True),
        "rag_subsystem_counts": summary.get("rag_subsystem_counts") or _count_values(
            case["model_rag"].get("rag_subsystem") for case in cases
        ),
        "selected_route_counts": _count_values(case["model_rag"].get("selected_route") for case in cases),
        "model_counts": model_counts,
        "model_recorded": sum(model_counts.values()),
        "model_missing": len(cases) - sum(model_counts.values()),
    }


def _failure_bucket(result: dict[str, Any], success: bool) -> str:
    if success:
        return "success"
    value = _first_present(
        result.get("run_failure_type"),
        result.get("failure_type"),
        result.get("failure_bucket"),
        result.get("build_failure_type"),
        result.get("validation_failure_type"),
    )
    if value:
        return str(value)
    if result.get("validation_status") and result.get("validation_status") != "passed":
        return f"validation_{result['validation_status']}"
    if result.get("run_status"):
        return str(result["run_status"])
    return "unknown"


def _model_rag(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_name": _first_present(
            result.get("model_name"),
            result.get("model"),
            result.get("llm_model"),
            result.get("bailian_model"),
        ),
        "selected_route": result.get("selected_route"),
        "preferred_route": result.get("preferred_route"),
        "rag_seed_hit": result.get("rag_seed_hit"),
        "rag_seed_group": result.get("rag_seed_group"),
        "rag_subsystem": result.get("rag_subsystem"),
        "rag_summary": result.get("rag_summary"),
    }


def _evidence_paths(result: dict[str, Any], manifest_entry: dict[str, Any] | None) -> dict[str, Any]:
    paths: dict[str, Any] = {}
    manifest_paths = (manifest_entry or {}).get("evidence_paths") if manifest_entry else None
    if isinstance(manifest_paths, dict):
        paths.update(manifest_paths)
    diagnostics = result.get("diagnostics") if isinstance(result.get("diagnostics"), dict) else {}
    for key, value in diagnostics.items():
        if isinstance(value, str) and (key.endswith("_path") or key.endswith("_paths")):
            paths.setdefault(key, value)
    return paths


def _count_values(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        if value is None or value == "":
            continue
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _target_gap_explanation(
    *,
    success_count: int,
    representative_total: int,
    success_rate: float,
    target_success_rate: float,
    average_attempts: float,
) -> dict[str, str]:
    target_percent = int(target_success_rate * 100)
    if representative_total == 0:
        return {
            "status": "no_cases",
            "explanation": f"代表集为空，无法对照赛题 {target_percent}%+ 热补丁成功率目标。",
        }
    if success_rate >= target_success_rate:
        return {
            "status": "meets_target",
            "explanation": (
                f"代表集 {success_count}/{representative_total} 成功，成功率 {success_rate:.1%}，"
                f"已达到赛题 {target_percent}%+ 目标；平均尝试轮次为 {average_attempts}。"
            ),
        }
    needed = _successes_needed(representative_total, target_success_rate)
    missing = max(0, needed - success_count)
    return {
        "status": "below_target",
        "explanation": (
            f"代表集 {success_count}/{representative_total} 成功，成功率 {success_rate:.1%}，"
            f"距离赛题 {target_percent}%+ 目标还差 {missing} 个成功样例；"
            f"平均尝试轮次为 {average_attempts}，需优先补齐失败样例的构建和验证证据。"
        ),
    }


def _successes_needed(total: int, target_success_rate: float) -> int:
    return int((total * target_success_rate) + 0.999999)


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _average(values: list[int]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def _manifest_entries_by_cve(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    manifest = _load_json_object(path)
    entries = _as_list(manifest.get("entries"))
    return {str(entry["cve_id"]): entry for entry in entries if isinstance(entry, dict) and entry.get("cve_id")}


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _first_path(value: Any) -> str | None:
    if isinstance(value, list) and value:
        return str(value[0])
    if isinstance(value, str):
        return value
    return None


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None
