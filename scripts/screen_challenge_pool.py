from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from patchweaver.harness.sample_pool import classify_sample_pool_result


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""

    parser = argparse.ArgumentParser(description="Challenge 样例分层与正向样例池筛选")
    parser.add_argument("--mode", choices=["analyze", "full"], default="analyze", help="筛选模式")
    parser.add_argument("--profile", default="dev", help="create 时使用的任务档位")
    parser.add_argument("--task-prefix", default="poolscan", help="任务编号前缀")
    parser.add_argument("--fixture", type=Path, help="读取 fixture 中的 CVE 列表")
    parser.add_argument("--output", type=Path, required=True, help="筛选结果输出路径")
    parser.add_argument("--cve", action="append", dest="cves", help="直接指定 CVE，可重复传入")
    parser.add_argument("--max-attempts", type=int, default=1, help="create 时写入的最大尝试次数")
    parser.add_argument("--python", default=sys.executable, help="调用 patchweaver CLI 的 Python 解释器")
    parser.add_argument("--run-timeout-sec", type=int, default=900, help="单条 run 命令的外层超时时间")
    parser.add_argument(
        "--only-positive-candidates",
        action="store_true",
        help="full 模式下只对低风险正向候选继续执行 run",
    )
    return parser.parse_args()


def load_cves(args: argparse.Namespace) -> list[str]:
    """整理待筛选的 CVE 列表"""

    cves: list[str] = []
    if args.fixture:
        payload = json.loads(args.fixture.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"fixture 格式不正确: {args.fixture}")
        cves.extend(str(item.get("cve_id") or "").strip() for item in payload if item.get("cve_id"))
    if args.cves:
        cves.extend(str(item).strip() for item in args.cves if str(item).strip())
    deduped: list[str] = []
    seen: set[str] = set()
    for cve in cves:
        if cve and cve not in seen:
            deduped.append(cve)
            seen.add(cve)
    if not deduped:
        raise ValueError("未提供任何 CVE")
    return deduped


def run_cli_json(*, python_bin: str, cwd: Path, cli_args: list[str], timeout_sec: int | None = None) -> dict[str, Any]:
    """执行 CLI 并读取 JSON 输出"""

    try:
        proc = subprocess.run(
            [python_bin, "-m", "patchweaver", *cli_args],
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        timeout_error = RuntimeError(
            f"命令超时: {' '.join(cli_args)}\nTIMEOUT: {timeout_sec}s\n"
            f"STDOUT:\n{exc.stdout or ''}\nSTDERR:\n{exc.stderr or ''}"
        )
        setattr(timeout_error, "timed_out", True)
        raise timeout_error
    if proc.returncode != 0:
        raise RuntimeError(f"命令失败: {' '.join(cli_args)}\nSTDERR:\n{proc.stderr}\nSTDOUT:\n{proc.stdout}")
    payload = extract_json_payload(proc.stdout)
    if not isinstance(payload, dict):
        raise RuntimeError(f"命令未返回 JSON 对象: {' '.join(cli_args)}\n{proc.stdout}")
    return payload


def extract_json_payload(text: str) -> Any:
    """从标准输出中提取 JSON 负载"""

    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char not in "{[":
            continue
        try:
            payload, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        return payload
    raise ValueError(f"未找到 JSON 负载\n{text}")


def runtime_paths(*, python_bin: str, cwd: Path) -> dict[str, Path]:
    """读取当前运行目录解析出的路径"""

    payload = run_cli_json(python_bin=python_bin, cwd=cwd, cli_args=["paths", "--json"])
    workspace_root = (cwd / str(payload.get("workspace_root") or "workspaces")).resolve()
    return {
        "project_root": cwd.resolve(),
        "workspace_root": workspace_root,
    }


def build_task_id(prefix: str, cve_id: str) -> str:
    """按固定规则生成任务编号"""

    suffix = cve_id.split("-")[-1]
    return f"{prefix}-{suffix}"


def load_analysis_artifacts(*, workspace_root: Path, task_id: str) -> dict[str, Any]:
    """读取 analyze 阶段产物"""

    analysis_dir = workspace_root / task_id / "analysis"
    constraint = json.loads((analysis_dir / "constraint_report.json").read_text(encoding="utf-8"))
    semantic = json.loads((analysis_dir / "semantic_card.json").read_text(encoding="utf-8"))
    return {
        "selected_route": constraint.get("preferred_route"),
        "preferred_route": constraint.get("preferred_route"),
        "direct_apply_viable": constraint.get("direct_apply_viable"),
        "high_risk_count": constraint.get("high_risk_count"),
        "dominant_risk_types": constraint.get("dominant_risk_types") or [],
        "requires_callback": constraint.get("requires_callback"),
        "requires_shadow_variable": constraint.get("requires_shadow_variable"),
        "summary": constraint.get("summary"),
        "target_files": constraint.get("target_files") or [],
        "critical_calls_count": len(semantic.get("critical_calls") or []),
        "key_conditions_count": len(semantic.get("must_keep_conditions") or []),
        "key_side_effects_count": len(semantic.get("must_keep_side_effects") or []),
    }


def load_full_artifacts(*, workspace_root: Path, task_id: str) -> dict[str, Any]:
    """读取 run 之后的产物"""

    attempt_dir = workspace_root / task_id / "attempts" / "001"
    build_summary = read_json_if_exists(attempt_dir / "artifacts" / "build_summary.json")
    validation_report = read_json_if_exists(attempt_dir / "artifacts" / "validation_report.json")
    failure_record = read_json_if_exists(attempt_dir / "logs" / "failure_record.json")
    return {
        "build_summary": build_summary,
        "validation_report": validation_report,
        "failure_record": failure_record,
        "build_status": str((build_summary or {}).get("status") or ""),
        "validation_status": str((validation_report or {}).get("status") or ""),
        "failure_type": str((failure_record or {}).get("failure_type") or (build_summary or {}).get("failure_type") or ""),
        "module_path": (build_summary or {}).get("module_path"),
    }


def read_json_if_exists(path: Path) -> dict[str, Any] | None:
    """按需读取 JSON 文件"""

    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    """汇总筛选结果"""

    bucket_counter = Counter(item.get("sample_bucket") or "unbucketed" for item in results)
    tier_counter = Counter(item.get("screening_tier") or "unknown" for item in results)
    role_counter = Counter(item.get("acceptance_role") or "unknown" for item in results)
    return {
        "total_cases": len(results),
        "bucket_counts": dict(bucket_counter),
        "tier_counts": dict(tier_counter),
        "role_counts": dict(role_counter),
        "confirmed_positive_acceptance": [
            item["cve_id"] for item in results if item.get("screening_tier") == "positive_acceptance_confirmed"
        ],
        "positive_pool_candidates": [
            item["cve_id"] for item in results if item.get("positive_pool_candidate")
        ],
        "stable_bucket_ready": [
            item["cve_id"] for item in results if item.get("stable_bucket_ready")
        ],
    }


def capture_failure_context(*, workspace_root: Path, task_id: str) -> dict[str, Any]:
    """抓取 run 失败或超时时的现场信息"""

    attempt_dir = workspace_root / task_id / "attempts" / "001"
    capture_dir = attempt_dir / "diagnostics"
    capture_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    ps_snapshot = collect_process_snapshot()
    copied_logs = copy_diagnostic_logs(attempt_dir=attempt_dir, capture_dir=capture_dir)
    snapshot_path = capture_dir / "process_snapshot.txt"
    snapshot_path.write_text(ps_snapshot, encoding="utf-8")
    return {
        "captured_at": timestamp,
        "diagnostics_dir": str(capture_dir),
        "process_snapshot_path": str(snapshot_path),
        "copied_logs": copied_logs,
    }


def collect_process_snapshot() -> str:
    """收集当前机器上和构建相关的进程"""

    if platform.system().lower().startswith("win"):
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Process | Where-Object { $_.ProcessName -match 'python|make|gcc|clang|kpatch' } | Select-Object ProcessName,Id,StartTime,CPU,Path | Format-Table -AutoSize"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    else:
        proc = subprocess.run(
            ["ps", "-eo", "pid,ppid,pgid,etime,cmd"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if proc.returncode == 0:
            lines = [
                line
                for line in proc.stdout.splitlines()
                if any(token in line for token in ["patchweaver", "kpatch-build", "make ", "gcc", "clang"])
            ]
            proc.stdout = "\n".join(lines) + ("\n" if lines else "")
    return proc.stdout or proc.stderr or ""


def copy_diagnostic_logs(*, attempt_dir: Path, capture_dir: Path) -> list[str]:
    """把关键日志复制到 diagnostics 目录"""

    copied: list[str] = []
    for relative in [
        Path("logs") / "build.log",
        Path("logs") / "failure_record.json",
        Path("artifacts") / "build_summary.json",
        Path("artifacts") / "validation_report.json",
        Path("trace") / "harness_trace.json",
    ]:
        source = attempt_dir / relative
        if not source.exists():
            continue
        target = capture_dir / relative.name
        target.write_bytes(source.read_bytes())
        copied.append(str(target))
    return copied


def run_create_analyze_phase(
    *,
    cves: list[str],
    args: argparse.Namespace,
    paths: dict[str, Path],
) -> list[dict[str, Any]]:
    """批量执行 create/analyze 并返回分析记录"""

    records: list[dict[str, Any]] = []
    for cve_id in cves:
        task_id = build_task_id(args.task_prefix, cve_id)
        record: dict[str, Any] = {
            "cve_id": cve_id,
            "task_id": task_id,
            "mode": args.mode,
            "profile": args.profile,
        }
        create_payload = run_cli_json(
            python_bin=args.python,
            cwd=PROJECT_ROOT,
            cli_args=[
                "create",
                "--cve",
                cve_id,
                "--profile",
                args.profile,
                "--max-attempts",
                str(args.max_attempts),
                "--task-id",
                task_id,
                "--force-new",
                "--json",
            ],
        )
        analyze_payload = run_cli_json(
            python_bin=args.python,
            cwd=PROJECT_ROOT,
            cli_args=["analyze", "--task", task_id, "--json"],
        )
        record["create_status"] = create_payload.get("status")
        record["analyze_status"] = analyze_payload.get("status")
        record.update(load_analysis_artifacts(workspace_root=paths["workspace_root"], task_id=task_id))
        record.update(classify_sample_pool_result(record))
        records.append(record)
    return records


def run_full_phase(*, records: list[dict[str, Any]], args: argparse.Namespace, paths: dict[str, Path]) -> list[dict[str, Any]]:
    """逐条执行 run/report/replay，run 自动带外层超时"""

    for record in records:
        if args.only_positive_candidates and not record.get("positive_pool_candidate"):
            record["run_skipped"] = "not_positive_candidate"
            continue

        task_id = str(record["task_id"])
        try:
            run_payload = run_cli_json(
                python_bin=args.python,
                cwd=PROJECT_ROOT,
                cli_args=["run", "--task", task_id, "--json"],
                timeout_sec=args.run_timeout_sec,
            )
            record.update(
                {
                    "run_status": run_payload.get("status"),
                    "run_failure_type": run_payload.get("failure_type"),
                    "build_exec_status": run_payload.get("build_exec_status"),
                    "target_state": run_payload.get("target_state"),
                }
            )
        except RuntimeError as exc:
            record.update(
                {
                    "run_status": "timeout" if getattr(exc, "timed_out", False) else "error",
                    "run_error": str(exc),
                }
            )
            record["diagnostics"] = capture_failure_context(workspace_root=paths["workspace_root"], task_id=task_id)

        for command_name in ["report", "replay"]:
            try:
                payload = run_cli_json(
                    python_bin=args.python,
                    cwd=PROJECT_ROOT,
                    cli_args=[command_name, "--task", task_id, "--json"],
                )
                record[f"{command_name}_status"] = payload.get("status")
            except RuntimeError as exc:
                record[f"{command_name}_status"] = "error"
                record[f"{command_name}_error"] = str(exc)

        record.update(load_full_artifacts(workspace_root=paths["workspace_root"], task_id=task_id))
        if (record.get("run_status") in {"failed", "timeout", "error"} or record.get("failure_type")) and "diagnostics" not in record:
            record["diagnostics"] = capture_failure_context(workspace_root=paths["workspace_root"], task_id=task_id)
        record.update(classify_sample_pool_result(record))
    return records


def main() -> int:
    """执行样例筛选"""

    args = parse_args()
    cves = load_cves(args)
    paths = runtime_paths(python_bin=args.python, cwd=PROJECT_ROOT)
    results = run_create_analyze_phase(cves=cves, args=args, paths=paths)
    if args.mode == "full":
        results = run_full_phase(records=results, args=args, paths=paths)

    payload = {
        "mode": args.mode,
        "profile": args.profile,
        "task_prefix": args.task_prefix,
        "run_timeout_sec": args.run_timeout_sec,
        "only_positive_candidates": args.only_positive_candidates,
        "project_root": str(paths["project_root"]),
        "workspace_root": str(paths["workspace_root"]),
        "summary": summarize(results),
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
