from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE_DIR = PROJECT_ROOT / "evaluations" / "fixtures"
DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "data" / "cache" / "p1_expansion_batch.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "data" / "cache" / "p1_expansion_batch.md"
BLOCKING_RECENT_FAILURES = {"target_already_patched", "stable_baseline_prepare_failed"}

MODULE_LIKE_PREFIXES = (
    "drivers/net",
    "drivers/hwmon",
    "drivers/media",
    "drivers/input",
    "drivers/usb",
    "drivers/phy",
    "drivers/pci",
    "drivers/iio",
    "drivers/rtc",
    "drivers/spi",
    "drivers/i2c",
    "net/",
    "fs/",
    "sound/",
)
LOW_PRIORITY_PREFIXES = (
    "vmlinux",
    "kernel/",
    "kernel",
    "mm/",
    "mm",
    "arch/",
    "arch",
    "include/",
    "include",
    "lib/",
    "lib",
)


@dataclass(frozen=True)
class Candidate:
    cve_id: str
    subsystem: str
    score: int
    reasons: list[str]
    suggested_command_fragment: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan the next small P1 positive-pool expansion batch from RAG seed fixtures.",
    )
    parser.add_argument(
        "--rag-seed",
        type=Path,
        default=DEFAULT_FIXTURE_DIR / "rag_seed_linux_kernel_2024_batch200.json",
        help="RAG seed fixture containing CVE, subsystem, and summary records.",
    )
    parser.add_argument(
        "--confirmed",
        type=Path,
        default=DEFAULT_FIXTURE_DIR / "challenge_positive_pool_confirmed_v0426.json",
        help="Confirmed positive-pool fixture to exclude.",
    )
    parser.add_argument(
        "--known-kpatch-constraint",
        type=Path,
        default=DEFAULT_FIXTURE_DIR / "challenge_kpatch_constraint_pool_v0427.json",
        help="Known kpatch-constraint fixture to exclude.",
    )
    parser.add_argument(
        "--already-patched",
        type=Path,
        default=DEFAULT_FIXTURE_DIR / "challenge_already_patched_pool_v0427.json",
        help="Known already-patched fixture to exclude.",
    )
    parser.add_argument(
        "--recent-full-run",
        type=Path,
        action="append",
        default=[],
        help="Optional recent screen_challenge_pool full-run JSON; repeatable.",
    )
    parser.add_argument("--max-candidates", type=int, default=12, help="Maximum candidates to emit.")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON, help="JSON plan output path.")
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD, help="Markdown plan output path.")
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_records(payload: Any) -> Iterable[dict[str, Any]]:
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield item
        return
    if not isinstance(payload, dict):
        return
    for key in ("results", "candidates", "items", "records", "fixtures"):
        value = payload.get(key)
        if isinstance(value, list):
            yield from iter_records(value)
            return
    if "cve_id" in payload:
        yield payload


def collect_cves(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {str(item["cve_id"]) for item in iter_records(load_json(path)) if item.get("cve_id")}


def collect_recent_failure_cves(paths: Iterable[Path]) -> set[str]:
    blocked: set[str] = set()
    for path in paths:
        if not path.exists():
            continue
        for item in iter_records(load_json(path)):
            failure = str(item.get("failure_type") or item.get("run_failure_type") or "")
            tier = str(item.get("screening_tier") or "")
            if failure in BLOCKING_RECENT_FAILURES or "stable_baseline_prepare_failed" in tier:
                cve_id = item.get("cve_id")
                if cve_id:
                    blocked.add(str(cve_id))
    return blocked


def score_record(record: dict[str, Any]) -> tuple[int, list[str]]:
    subsystem = str(record.get("subsystem") or record.get("rag_subsystem") or "").strip()
    normalized = subsystem.lower()
    summary = str(record.get("summary") or "").lower()
    score = 50
    reasons: list[str] = []

    if normalized.startswith(MODULE_LIKE_PREFIXES):
        score += 35
        reasons.append("module-like subsystem")
    if normalized.startswith(LOW_PRIORITY_PREFIXES):
        score -= 30
        reasons.append("lower priority vmlinux/core subsystem")
    if any(token in summary for token in ("fix null", "null pointer", "bounds", "oob", "use-after-free", "leak")):
        score += 8
        reasons.append("localized fix-like summary")
    if normalized.startswith(("drivers/net", "drivers/usb", "drivers/hwmon", "drivers/media", "drivers/input")):
        score += 8
        reasons.append("preferred P1 expansion subsystem")
    if not reasons:
        reasons.append("not in exclusion pools")

    return max(score, 0), reasons


def command_fragment(cve_id: str) -> str:
    return f"--mode full --fixture evaluations/fixtures/rag_seed_linux_kernel_2024_batch200.json --cve {cve_id}"


def plan_candidates(
    *,
    rag_seed_path: Path,
    confirmed_path: Path,
    known_kpatch_constraint_path: Path,
    already_patched_path: Path,
    recent_full_run_paths: Iterable[Path],
    max_candidates: int,
) -> tuple[list[Candidate], dict[str, Any]]:
    excluded_confirmed = collect_cves(confirmed_path)
    excluded_kpatch = collect_cves(known_kpatch_constraint_path)
    excluded_already_patched = collect_cves(already_patched_path)
    excluded_recent_failures = collect_recent_failure_cves(recent_full_run_paths)
    excluded = excluded_confirmed | excluded_kpatch | excluded_already_patched | excluded_recent_failures

    candidates: list[Candidate] = []
    seen: set[str] = set()
    for record in iter_records(load_json(rag_seed_path)):
        cve_id = str(record.get("cve_id") or "")
        if not cve_id or cve_id in seen or cve_id in excluded:
            continue
        seen.add(cve_id)
        score, reasons = score_record(record)
        candidates.append(
            Candidate(
                cve_id=cve_id,
                subsystem=str(record.get("subsystem") or record.get("rag_subsystem") or ""),
                score=score,
                reasons=reasons,
                suggested_command_fragment=command_fragment(cve_id),
            )
        )

    candidates.sort(key=lambda item: (-item.score, item.cve_id))
    selected = candidates[:max_candidates]
    summary = {
        "rag_seed_count": len(list(iter_records(load_json(rag_seed_path)))),
        "excluded_confirmed_count": len(excluded_confirmed),
        "excluded_kpatch_constraint_count": len(excluded_kpatch),
        "excluded_already_patched_count": len(excluded_already_patched),
        "excluded_recent_failure_count": len(excluded_recent_failures),
        "candidate_count": len(candidates),
        "selected_count": len(selected),
    }
    return selected, summary


def build_payload(candidates: list[Candidate], summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": summary,
        "rules": {
            "excluded_recent_failures": sorted(BLOCKING_RECENT_FAILURES),
            "preferred_subsystems": list(MODULE_LIKE_PREFIXES[:5]),
            "lower_priority_subsystems": list(LOW_PRIORITY_PREFIXES),
        },
        "candidates": [asdict(candidate) for candidate in candidates],
    }


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# P1 Expansion Batch Plan",
        "",
        "## Summary",
        "",
        f"- Selected candidates: {payload['summary']['selected_count']}",
        f"- Candidate pool after exclusions: {payload['summary']['candidate_count']}",
        f"- Excluded confirmed positives: {payload['summary']['excluded_confirmed_count']}",
        f"- Excluded known kpatch constraints: {payload['summary']['excluded_kpatch_constraint_count']}",
        f"- Excluded already patched: {payload['summary']['excluded_already_patched_count']}",
        f"- Excluded recent terminal failures: {payload['summary']['excluded_recent_failure_count']}",
        "",
        "## Candidates",
        "",
        "| CVE | Subsystem | Score | Reasons | Suggested command fragment |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for item in payload["candidates"]:
        reasons = ", ".join(item["reasons"])
        lines.append(
            f"| {item['cve_id']} | {item['subsystem']} | {item['score']} | {reasons} | `{item['suggested_command_fragment']}` |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    candidates, summary = plan_candidates(
        rag_seed_path=args.rag_seed,
        confirmed_path=args.confirmed,
        known_kpatch_constraint_path=args.known_kpatch_constraint,
        already_patched_path=args.already_patched,
        recent_full_run_paths=args.recent_full_run,
        max_candidates=args.max_candidates,
    )
    payload = build_payload(candidates, summary)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    write_markdown(args.output_md, payload)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
