from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from patchweaver.harness.livepatchability import analyze_patch_shape
from patchweaver.harness.semantic_guard_screening import (
    SemanticGuardCandidate,
    build_semantic_guard_candidate,
    read_json_if_exists,
    sort_candidates,
)


DEFAULT_RAG_SEED = PROJECT_ROOT / "evaluations" / "fixtures" / "rag_seed_linux_kernel_2024_batch200.json"


def parse_args() -> argparse.Namespace:
    """Parse semantic guard screening options."""

    parser = argparse.ArgumentParser(description="筛选 semantic_guard_rewrite 高适配候选")
    parser.add_argument("--artifact-root", action="append", type=Path, help="分析产物根目录，可重复指定")
    parser.add_argument("--rag-seed-fixture", type=Path, default=DEFAULT_RAG_SEED, help="RAG seed fixture")
    parser.add_argument("--output", type=Path, required=True, help="候选 JSON 输出路径")
    parser.add_argument("--report-md", type=Path, help="候选 Markdown 报告输出路径")
    parser.add_argument("--min-confidence", type=float, default=0.55, help="候选最低置信度")
    parser.add_argument("--max-candidates", type=int, default=20, help="最多输出候选数")
    parser.add_argument("--cve", action="append", dest="cves", help="只筛指定 CVE，可重复传入")
    parser.add_argument(
        "--include-rag-seed-only",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="是否把 RAG seed 摘要作为无 patch 的轻量候选来源",
    )
    parser.add_argument(
        "--validation-mode",
        choices=["none", "dry-run", "analyze"],
        default="none",
        help="可选验证机小规模入口；默认不触发验证机",
    )
    parser.add_argument("--validation-cve", action="append", dest="validation_cves", help="指定 1-2 条 CVE 进入验证入口")
    parser.add_argument("--remote-host", default="10.223.185.3", help="验证机 host")
    parser.add_argument("--remote-user", default="root", help="验证机用户")
    parser.add_argument("--remote-project-root", default="/home/patchweaver/current", help="验证机项目目录")
    parser.add_argument("--remote-python", default="python", help="验证机 Python 命令")
    parser.add_argument("--remote-profile", default="dev", help="验证机 create profile")
    parser.add_argument("--remote-task-prefix", default="sgscreen", help="验证机 task id 前缀")
    parser.add_argument("--remote-timeout-sec", type=int, default=600, help="单条远端 create+analyze timeout")
    parser.add_argument("--ssh-password", default=os.getenv("PATCHWEAVER_VALIDATION_PASSWORD"), help="可选 sshpass 密码")
    return parser.parse_args()


def load_rag_seed_index(path: Path | None) -> dict[str, dict[str, Any]]:
    """Load RAG seed rows keyed by CVE id."""

    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return {}
    index: dict[str, dict[str, Any]] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        cve_id = str(item.get("cve_id") or "").strip()
        if cve_id:
            index[cve_id] = item
    return index


def discover_artifact_dirs(roots: list[Path]) -> list[Path]:
    """Discover directories that contain analysis or cached screening artifacts."""

    dirs: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        if _looks_artifact_dir(root):
            dirs.append(root)
            continue
        for child in root.rglob("*"):
            if child.is_dir() and _looks_artifact_dir(child):
                dirs.append(child)
    return _drop_nested_artifact_dirs(sorted(set(dirs)))


def load_record(artifact_dir: Path, rag_seed_index: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """Load one candidate record from a cache or workspace artifact dir."""

    task_context = read_json_if_exists(artifact_dir / "task_context.json")
    patch_bundle = read_json_if_exists(artifact_dir / "input" / "patch_bundle.json")
    if not patch_bundle:
        patch_bundle = read_json_if_exists(artifact_dir / "patch_bundle.json")
    semantic_card = read_json_if_exists(artifact_dir / "analysis" / "semantic_card.json")
    if not semantic_card:
        semantic_card = read_json_if_exists(artifact_dir / "semantic_card.json")
    constraint_report = read_json_if_exists(artifact_dir / "analysis" / "constraint_report.json")
    if not constraint_report:
        constraint_report = read_json_if_exists(artifact_dir / "constraint_report.json")
    rewrite_plan = read_json_if_exists(artifact_dir / "attempts" / "001" / "rewrite" / "rewrite_plan.json")
    if not rewrite_plan:
        rewrite_plan = read_json_if_exists(artifact_dir / "rewrite_plan.json")

    cve_id = str(
        task_context.get("cve_id")
        or patch_bundle.get("cve_id")
        or read_json_if_exists(artifact_dir / "source_fetch_trace.json").get("cve_id")
        or ""
    ).strip()
    if not cve_id:
        return None
    patch_text = read_patch_text(artifact_dir, patch_bundle)
    patch_shape = analyze_patch_shape(patch_text) if patch_text else {}
    return {
        "cve_id": cve_id,
        "task_id": str(task_context.get("task_id") or patch_bundle.get("task_id") or artifact_dir.name),
        "artifact_dir": str(artifact_dir),
        "patch_bundle": patch_bundle,
        "semantic_card": semantic_card,
        "constraint_report": constraint_report,
        "rewrite_plan": rewrite_plan,
        "patch_text": patch_text,
        "patch_shape": patch_shape,
        "affected_files": patch_bundle.get("affected_files") or semantic_card.get("touched_files") or constraint_report.get("target_files") or [],
        "rag_seed": rag_seed_index.get(cve_id, {}),
    }


def read_patch_text(artifact_dir: Path, patch_bundle: dict[str, Any]) -> str:
    """Read normalized or raw patch text from common artifact locations."""

    candidate_paths = [
        artifact_dir / "normalized" / "normalized.patch",
        artifact_dir / "input" / "normalized.patch",
        artifact_dir / "input" / "raw_patch.patch",
        artifact_dir / "raw_patch.patch",
        artifact_dir / "normalized.patch",
    ]
    for key in ["normalized_patch_path", "raw_patch_path"]:
        raw = patch_bundle.get(key)
        if raw:
            candidate_paths.append(Path(str(raw)))
    for path in candidate_paths:
        if path.exists() and path.is_file():
            return path.read_text(encoding="utf-8", errors="replace")
    return ""


def screen_records(
    records: list[dict[str, Any]],
    *,
    min_confidence: float,
    max_candidates: int,
    cves: list[str] | None,
) -> list[SemanticGuardCandidate]:
    """Classify records and return sorted candidates."""

    cve_filter = {item.strip() for item in cves or [] if item.strip()}
    candidates: list[SemanticGuardCandidate] = []
    best_by_cve: dict[str, SemanticGuardCandidate] = {}
    for record in records:
        if cve_filter and record["cve_id"] not in cve_filter:
            continue
        candidate = build_semantic_guard_candidate(record, min_confidence=min_confidence)
        if candidate is None:
            continue
        previous = best_by_cve.get(candidate.cve_id)
        if previous is None or candidate.confidence > previous.confidence:
            best_by_cve[candidate.cve_id] = candidate
    candidates.extend(best_by_cve.values())
    return sort_candidates(candidates)[:max_candidates]


def build_rag_seed_records(seed_index: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert RAG seed rows into lightweight screening records."""

    records: list[dict[str, Any]] = []
    for cve_id, seed in seed_index.items():
        subsystem = str(seed.get("subsystem") or "").strip()
        summary = str(seed.get("summary") or "").strip()
        records.append(
            {
                "cve_id": cve_id,
                "task_id": "rag-seed-only",
                "artifact_dir": str(DEFAULT_RAG_SEED),
                "patch_text": "",
                "patch_bundle": {
                    "cve_id": cve_id,
                    "commit_message": summary,
                    "affected_files": [subsystem] if subsystem else [],
                },
                "semantic_card": {
                    "root_cause": summary,
                    "touched_files": [subsystem] if subsystem else [],
                },
                "constraint_report": {},
                "rewrite_plan": {},
                "affected_files": [subsystem] if subsystem else [],
                "rag_seed": seed,
            }
        )
    return records


def build_validation_plan(args: argparse.Namespace, candidates: list[SemanticGuardCandidate]) -> dict[str, Any]:
    """Prepare or run the explicitly bounded validation-machine entry."""

    selected_cves = [item.strip() for item in args.validation_cves or [] if item.strip()]
    if not selected_cves and args.validation_mode in {"dry-run", "analyze"}:
        selected_cves = [candidate.cve_id for candidate in candidates[:2]]
    selected_cves = list(dict.fromkeys(selected_cves))
    if len(selected_cves) > 2:
        raise ValueError("--validation-cve 最多允许指定 2 条，避免误触发大规模验证")
    commands = [build_remote_analyze_command(args, cve_id) for cve_id in selected_cves]
    payload: dict[str, Any] = {
        "mode": args.validation_mode,
        "selected_cves": selected_cves,
        "commands": commands,
        "executed": False,
        "results": [],
    }
    if args.validation_mode != "analyze":
        return payload
    results = []
    for command in commands:
        proc = run_remote_command(args, command)
        results.append(
            {
                "command": command,
                "returncode": proc.returncode,
                "stdout_tail": "\n".join((proc.stdout or "").splitlines()[-40:]),
                "stderr_tail": "\n".join((proc.stderr or "").splitlines()[-40:]),
            }
        )
    payload["executed"] = True
    payload["results"] = results
    return payload


def build_remote_analyze_command(args: argparse.Namespace, cve_id: str) -> str:
    """Build a remote create+analyze command for one CVE."""

    suffix = cve_id.split("-")[-1]
    task_id = f"{args.remote_task_prefix}-{suffix}"
    create_cmd = (
        f"{args.remote_python} -m patchweaver create --cve {cve_id} --profile {args.remote_profile} "
        f"--task-id {task_id} --force-new --json"
    )
    analyze_cmd = f"{args.remote_python} -m patchweaver analyze --task {task_id} --json"
    return f"cd {args.remote_project_root} && timeout {int(args.remote_timeout_sec)}s sh -lc '{create_cmd} && {analyze_cmd}'"


def run_remote_command(args: argparse.Namespace, command: str) -> subprocess.CompletedProcess[str]:
    """Run a remote command through ssh or sshpass."""

    target = f"{args.remote_user}@{args.remote_host}"
    base = ["ssh", "-o", "StrictHostKeyChecking=no", target, command]
    if args.ssh_password:
        base = ["sshpass", "-p", args.ssh_password, *base]
    return subprocess.run(
        base,
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        timeout=max(30, int(args.remote_timeout_sec) + 60),
        check=False,
    )


def write_markdown_report(path: Path, payload: dict[str, Any]) -> None:
    """Write a compact Markdown candidate report."""

    lines = [
        "# semantic_guard_rewrite 候选筛选报告",
        "",
        "## 汇总",
        "",
        f"- generated_at: `{payload['generated_at']}`",
        f"- total_records: `{payload['summary']['total_records']}`",
        f"- candidate_count: `{payload['summary']['candidate_count']}`",
        f"- validation_mode: `{payload['validation']['mode']}`",
        f"- validation_executed: `{payload['validation']['executed']}`",
        "",
        "## 候选",
        "",
        "| CVE | category | confidence | affected_files | validation | reason |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in payload["candidates"]:
        lines.append(
            "| {cve} | `{cat}` | `{conf}` | `{files}` | `{mode}` | {reason} |".format(
                cve=item["cve_id"],
                cat=item["guard_category"],
                conf=item["confidence"],
                files=", ".join(item.get("affected_files") or []),
                mode=item["suggested_validation_mode"],
                reason=str(item["reason"]).replace("|", "/"),
            )
        )
    lines.extend(["", "## 小规模验证入口", ""])
    for command in payload["validation"]["commands"]:
        lines.append(f"- `{command}`")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _looks_artifact_dir(path: Path) -> bool:
    return any(
        (path / relative).exists()
        for relative in [
            Path("semantic_card.json"),
            Path("analysis") / "semantic_card.json",
            Path("constraint_report.json"),
            Path("analysis") / "constraint_report.json",
            Path("input") / "patch_bundle.json",
        ]
    )


def _drop_nested_artifact_dirs(paths: list[Path]) -> list[Path]:
    """Prefer task/cache roots over nested analysis directories."""

    kept: list[Path] = []
    for path in sorted(paths, key=lambda item: len(item.parts)):
        if any(_is_relative_to(path, parent) for parent in kept):
            continue
        kept.append(path)
    return sorted(kept)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return path != parent


def main() -> int:
    """Run semantic guard candidate screening."""

    args = parse_args()
    artifact_roots = args.artifact_root or [
        PROJECT_ROOT / "workspaces",
        PROJECT_ROOT / "data" / "cache" / "5newcve_round0426d_artifacts",
        PROJECT_ROOT / "data" / "cache" / "5newcve_round0426c_artifacts",
    ]
    rag_seed_index = load_rag_seed_index(args.rag_seed_fixture)
    artifact_dirs = discover_artifact_dirs(artifact_roots)
    records = [record for path in artifact_dirs if (record := load_record(path, rag_seed_index)) is not None]
    if args.include_rag_seed_only:
        seen_cves = {str(record.get("cve_id") or "") for record in records}
        records.extend(record for record in build_rag_seed_records(rag_seed_index) if record["cve_id"] not in seen_cves)
    candidates = screen_records(
        records,
        min_confidence=args.min_confidence,
        max_candidates=args.max_candidates,
        cves=args.cves,
    )
    validation = build_validation_plan(args, candidates)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "artifact_roots": [str(path) for path in artifact_roots],
        "rag_seed_fixture": str(args.rag_seed_fixture),
        "summary": {
            "total_records": len(records),
            "candidate_count": len(candidates),
            "guard_category_counts": _count_by([candidate.guard_category for candidate in candidates]),
        },
        "candidates": [candidate.to_dict() for candidate in candidates],
        "validation": validation,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.report_md:
        write_markdown_report(args.report_md, payload)
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    return 0


def _count_by(values: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


if __name__ == "__main__":
    raise SystemExit(main())
