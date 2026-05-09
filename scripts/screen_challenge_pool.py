from __future__ import annotations

import argparse
import json
import platform
import os
import signal
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from patchweaver.builder.config_repair import infer_minimal_config_delta, render_config_fragment
from patchweaver.builder.orchestrator import BuildOrchestrator
from patchweaver.config.loader import load_build_config
from patchweaver.harness.livepatchability import apply_livepatchability_gate, load_patch_shape
from patchweaver.harness.sample_pool import classify_sample_pool_result


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""

    parser = argparse.ArgumentParser(description="Challenge 样例分层与正向样例池筛选")
    parser.add_argument("--mode", choices=["analyze", "full"], default="analyze", help="筛选模式")
    parser.add_argument("--profile", default="dev", help="create 时使用的任务档位")
    parser.add_argument("--task-prefix", default="poolscan", help="任务编号前缀")
    parser.add_argument("--fixture", type=Path, help="读取 fixture 中的 CVE 列表")
    parser.add_argument("--output", type=Path, required=True, help="筛选结果输出路径")
    parser.add_argument("--report-md", type=Path, help="额外输出 Markdown 筛选报告")
    parser.add_argument("--cve", action="append", dest="cves", help="直接指定 CVE，可重复传入")
    parser.add_argument("--start-index", type=int, default=0, help="从 fixture 去重后的第几条开始筛选，适合分批扫描")
    parser.add_argument("--max-cases", type=int, help="最多筛选多少条 CVE，适合验证机分批执行")
    parser.add_argument("--max-attempts", type=int, help="create 时写入的最大尝试次数，未指定时沿用 profile 默认值")
    parser.add_argument("--max-run-attempts", type=int, help="full 模式下每条 CVE 最多执行多少轮 run")
    parser.add_argument("--python", default=sys.executable, help="调用 patchweaver CLI 的 Python 解释器")
    parser.add_argument("--create-timeout-sec", type=int, default=120, help="单条 create 命令的外层超时时间")
    parser.add_argument("--analyze-timeout-sec", type=int, default=600, help="单条 analyze 命令的外层超时时间")
    parser.add_argument("--run-timeout-sec", type=int, default=900, help="单条 run 命令的外层超时时间")
    parser.add_argument(
        "--stable-baseline-timeout-sec",
        type=int,
        default=600,
        help="单条 prepare-stable-baseline 命令的外层超时时间",
    )
    parser.add_argument("--stable-source-git-dir", type=Path, help="显式指定 linux-stable git 仓库路径")
    parser.add_argument("--stable-source-cache-dir", type=Path, help="显式指定 stable baseline 缓存根目录")
    parser.add_argument("--stable-config-source", type=Path, help="显式指定 stable baseline 使用的 .config 来源")
    parser.add_argument("--screening-round", default=datetime.now().strftime("v%m%d"), help="写入 fixture 时使用的筛选轮次")
    parser.add_argument("--positive-pool-target", type=int, default=10, help="正向池阶段目标数量，用于输出缺口")
    parser.add_argument(
        "--prepare-stable-baseline",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="full 模式下按 stable_source_baseline_ref 自动准备未修复 stable source baseline",
    )
    parser.add_argument(
        "--config-fragment-dir",
        type=Path,
        help="写出 minimal config repair 的 .config.fragment 目录，默认跟随 output 生成",
    )
    parser.add_argument(
        "--rag-seed-fixture",
        type=Path,
        default=PROJECT_ROOT / "evaluations" / "fixtures" / "rag_seed_linux_kernel_2024_batch200.json",
        help="RAG 种子样例 fixture，用于给候选补充 subsystem 和摘要来源",
    )
    parser.add_argument(
        "--positive-pool-fixture",
        type=Path,
        default=PROJECT_ROOT / "evaluations" / "fixtures" / "challenge_positive_pool_confirmed_v0426.json",
        help="正向样例池 fixture 路径",
    )
    parser.add_argument(
        "--known-kpatch-constraint-fixture",
        type=Path,
        default=PROJECT_ROOT / "evaluations" / "fixtures" / "challenge_kpatch_constraint_pool_v0427.json",
        help="已知 kpatch_constraint 专项池 fixture 路径，正向池扩展时用于排除专项样例",
    )
    parser.add_argument(
        "--include-known-pool-cases",
        action="store_true",
        help="正向池扩展时仍保留已确认正向样例和已知 kpatch_constraint 样例，默认会过滤",
    )
    parser.add_argument(
        "--update-positive-pool",
        action="store_true",
        help="把 full 模式确认成功的样例追加到正向池 fixture",
    )
    parser.add_argument(
        "--only-positive-candidates",
        action="store_true",
        help="full 模式下只对低风险正向候选继续执行 run",
    )
    parser.add_argument(
        "--only-module-target-candidates",
        action="store_true",
        help="只让能推导到具体 .ko 模块目标的候选进入快速正向池筛选",
    )
    parser.add_argument(
        "--min-livepatchability-score",
        type=int,
        default=75,
        help="livepatchability-first 筛选进入 full run 的最低分",
    )
    parser.add_argument(
        "--only-high-livepatchability",
        action="store_true",
        help="只让 livepatchability 高分候选进入 full run",
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
    if args.start_index > 0:
        deduped = deduped[args.start_index :]
    if args.max_cases is not None and args.max_cases > 0:
        deduped = deduped[: args.max_cases]
    return deduped


def run_cli_json(*, python_bin: str, cwd: Path, cli_args: list[str], timeout_sec: int | None = None) -> dict[str, Any]:
    """执行 CLI 并读取 JSON 输出"""

    try:
        proc = run_command_with_process_group(
            [python_bin, "-m", "patchweaver", *cli_args],
            cwd=cwd,
            timeout_sec=timeout_sec,
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


def run_command_with_process_group(
    command: list[str],
    *,
    cwd: Path,
    timeout_sec: int | None,
) -> subprocess.CompletedProcess[str]:
    """执行命令，超时时清理整棵子进程树"""

    popen_kwargs: dict[str, Any] = {}
    if platform.system().lower().startswith("win"):
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True

    proc = subprocess.Popen(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        **popen_kwargs,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout_sec)
    except subprocess.TimeoutExpired as exc:
        cleanup_process_tree(proc)
        stdout, stderr = proc.communicate(timeout=30)
        timeout_exc = subprocess.TimeoutExpired(command, timeout_sec, output=stdout, stderr=stderr)
        raise timeout_exc from exc
    return subprocess.CompletedProcess(command, proc.returncode, stdout, stderr)


def cleanup_process_tree(proc: subprocess.Popen[str]) -> None:
    """清理被外层 timeout 截断的 CLI 进程树"""

    if proc.poll() is not None:
        return
    if platform.system().lower().startswith("win"):
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    pgids = collect_posix_descendant_process_groups(proc.pid)
    pgids.add(proc.pid)
    terminate_posix_process_groups(pgids, signal.SIGTERM)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        terminate_posix_process_groups(pgids, signal.SIGKILL)


def collect_posix_descendant_process_groups(root_pid: int) -> set[int]:
    """收集 root_pid 下面所有子进程所在的 POSIX 进程组"""

    try:
        snapshot = subprocess.run(
            ["ps", "-eo", "pid=,ppid=,pgid="],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        ).stdout
    except OSError:
        return set()
    return parse_posix_descendant_process_groups(root_pid=root_pid, ps_output=snapshot)


def parse_posix_descendant_process_groups(root_pid: int, ps_output: str) -> set[int]:
    """从 ps 输出里推导 descendant PGID，覆盖子进程自行 setsid 的情况"""

    children_by_parent: dict[int, list[tuple[int, int]]] = {}
    for line in ps_output.splitlines():
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        try:
            pid = int(parts[0])
            ppid = int(parts[1])
            pgid = int(parts[2])
        except ValueError:
            continue
        children_by_parent.setdefault(ppid, []).append((pid, pgid))

    pgids: set[int] = set()
    pending = [root_pid]
    seen: set[int] = set()
    while pending:
        parent = pending.pop()
        if parent in seen:
            continue
        seen.add(parent)
        for child_pid, child_pgid in children_by_parent.get(parent, []):
            if child_pgid > 0:
                pgids.add(child_pgid)
            pending.append(child_pid)
    return pgids


def terminate_posix_process_groups(pgids: set[int], sig: signal.Signals) -> None:
    """逐个终止进程组，避免 timeout 后留下 kpatch-build 或 make"""

    for pgid in sorted(pgids, reverse=True):
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            continue
        except OSError:
            continue


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

    task_dir = workspace_root / task_id
    analysis_dir = workspace_root / task_id / "analysis"
    constraint = json.loads((analysis_dir / "constraint_report.json").read_text(encoding="utf-8"))
    semantic = json.loads((analysis_dir / "semantic_card.json").read_text(encoding="utf-8"))
    patch_bundle = read_json_if_exists(task_dir / "input" / "patch_bundle.json") or {}
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
        "target_function_count": len(semantic.get("touched_functions") or []),
        "stable_source_baseline_ref": patch_bundle.get("stable_source_baseline_ref"),
        "patch_shape": load_patch_shape(task_dir / "normalized" / "normalized.patch"),
    }


def load_rag_seed_index(path: Path | None) -> dict[str, dict[str, Any]]:
    """读取 RAG seed fixture，供筛样记录补充来源信息"""

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


def annotate_with_rag_seed(records: list[dict[str, Any]], seed_index: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """把 RAG seed 中的 subsystem 和摘要写回筛样记录"""

    for record in records:
        seed = seed_index.get(str(record.get("cve_id") or ""))
        if not seed:
            record["rag_seed_hit"] = False
            continue
        record["rag_seed_hit"] = True
        record["rag_seed_group"] = seed.get("seed_group")
        record["rag_subsystem"] = seed.get("subsystem")
        record["rag_summary"] = seed.get("summary")
    return records


def load_known_pool_cves(path: Path | None) -> set[str]:
    """读取已知池中的 CVE 编号"""

    if path is None or not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return set()
    return {
        str(item.get("cve_id") or "").strip()
        for item in payload
        if isinstance(item, dict) and str(item.get("cve_id") or "").strip()
    }


def apply_known_pool_gate(
    records: list[dict[str, Any]],
    *,
    positive_pool_fixture: Path,
    known_kpatch_constraint_fixture: Path,
) -> list[dict[str, Any]]:
    """正向池扩展时过滤已经有明确归属的样例"""

    known_positive = load_known_pool_cves(positive_pool_fixture)
    known_kpatch_constraints = load_known_pool_cves(known_kpatch_constraint_fixture)
    for record in records:
        cve_id = str(record.get("cve_id") or "").strip()
        if not cve_id:
            continue
        if cve_id in known_positive:
            record.update(
                {
                    "known_pool_hit": "positive_pool",
                    "sample_bucket": "buildable_and_should_pass",
                    "acceptance_role": "positive_acceptance_sample",
                    "screening_tier": "positive_candidate_already_confirmed",
                    "reason": "该 CVE 已在 confirmed 正向池中，本轮扩池不重复执行",
                    "stable_bucket_ready": True,
                    "positive_pool_candidate": False,
                }
            )
            continue
        if cve_id in known_kpatch_constraints:
            record.update(
                {
                    "known_pool_hit": "kpatch_constraint_pool",
                    "sample_bucket": "kpatch_constraint",
                    "acceptance_role": "blocked_sample",
                    "screening_tier": "blocked_by_known_kpatch_constraint",
                    "reason": "该 CVE 已在 kpatch_constraint 专项池中，扩正向池时不混入成功率统计",
                    "stable_bucket_ready": True,
                    "positive_pool_candidate": False,
                }
            )
    return records


def load_full_artifacts(*, workspace_root: Path, task_id: str) -> dict[str, Any]:
    """读取 run 之后的产物"""

    attempt_dir = latest_attempt_dir(workspace_root=workspace_root, task_id=task_id)
    build_summary = read_json_if_exists(attempt_dir / "artifacts" / "build_summary.json")
    validation_report = read_json_if_exists(attempt_dir / "artifacts" / "validation_report.json")
    failure_record = read_json_if_exists(attempt_dir / "logs" / "failure_record.json")
    patch_apply_details = (
        ((failure_record or {}).get("diagnostic_details") or {}).get("patch_apply") or {}
        if isinstance((failure_record or {}).get("diagnostic_details"), dict)
        else {}
    )
    agent_next_action = (
        ((failure_record or {}).get("diagnostic_details") or {}).get("agent_next_action") or {}
        if isinstance((failure_record or {}).get("diagnostic_details"), dict)
        else {}
    )
    module_file = resolve_module_path((build_summary or {}).get("module_path"), attempt_dir=attempt_dir)
    module_vermagic = read_module_vermagic(module_file)
    payload = {
        "latest_attempt_dir": str(attempt_dir),
        "build_summary": build_summary,
        "validation_report": validation_report,
        "failure_record": failure_record,
        "build_status": str((build_summary or {}).get("status") or ""),
        "validation_status": str((validation_report or {}).get("status") or ""),
        "module_path": str(module_file) if module_file is not None else (build_summary or {}).get("module_path"),
        "module_exists": bool(module_file is not None and module_file.exists()),
        "module_vermagic": module_vermagic,
        "target_kernel_release": platform.release(),
        "patch_apply_subtype": patch_apply_details.get("subtype"),
        "reverse_unpatch_status": patch_apply_details.get("reverse_unpatch_status"),
        "stable_source_alignment_required": bool(patch_apply_details.get("stable_source_alignment_required")),
        "stable_source_baseline_action": patch_apply_details.get("stable_source_baseline_action"),
        "agent_next_action": agent_next_action.get("action") if isinstance(agent_next_action, dict) else None,
    }
    failure_type = str((failure_record or {}).get("failure_type") or (build_summary or {}).get("failure_type") or "")
    if failure_type:
        payload["failure_type"] = failure_type
    return payload


def apply_module_target_gate(records: list[dict[str, Any]], *, project_root: Path) -> list[dict[str, Any]]:
    """只保留能映射到具体 .ko 的快速正向候选"""

    build_config = load_build_config(project_root)
    source_dir = _select_target_inference_source(build_config)
    orchestrator = BuildOrchestrator(build_config)
    config_values = orchestrator._load_kernel_config_values(source_dir) if source_dir is not None else {}
    for record in records:
        target_files = [Path(str(item)) for item in record.get("target_files") or []]
        target_infos = infer_build_targets_for_record(
            orchestrator=orchestrator,
            source_dir=source_dir,
            config_values=config_values,
            target_files=target_files,
        )
        record["inferred_build_targets"] = [item["target"] for item in target_infos]
        record["build_target_states"] = [item["state"] for item in target_infos]
        record["inferred_build_target_details"] = target_infos
        record["module_target_candidate"] = any(
            str(item["target"]).endswith(".ko") and item["state"] == "module" for item in target_infos
        )
        record["vmlinux_target_candidate"] = any(item["target"] == "vmlinux" for item in target_infos)
        minimal_config_repair = infer_minimal_config_delta(source_dir=source_dir, target_files=target_files)
        record["minimal_config_repair"] = minimal_config_repair
        record["minimal_config_fragment"] = render_config_fragment(
            dict(minimal_config_repair.get("config_delta") or {})
        )

        if not record.get("positive_pool_candidate"):
            continue
        if record["module_target_candidate"]:
            continue
        if any(item["state"] == "disabled" for item in target_infos):
            record.update(
                {
                    "sample_bucket": "feature_not_enabled",
                    "acceptance_role": "development_sample",
                    "screening_tier": "development_only_feature_gate",
                    "reason": "目标文件在当前验证机配置下不可构建，先归入配置门控回归",
                    "stable_bucket_ready": True,
                    "positive_pool_candidate": False,
                }
            )
            continue
        record.update(
            {
                "sample_bucket": None,
                "acceptance_role": "deferred_sample",
                "screening_tier": "deferred_vmlinux_target",
                "reason": "低风险候选落到 vmlinux 或未知构建目标，本轮快速扩池只推进具体 .ko 模块目标",
                "stable_bucket_ready": False,
                "positive_pool_candidate": False,
            }
        )
    return records


def write_minimal_config_fragments(*, records: list[dict[str, Any]], fragment_dir: Path) -> list[str]:
    """把可修复 CONFIG delta 写成可复测 .config.fragment"""

    written: list[str] = []
    for record in records:
        repair = record.get("minimal_config_repair")
        if not isinstance(repair, dict) or repair.get("status") != "repairable":
            continue
        fragment = str(record.get("minimal_config_fragment") or "")
        if not fragment.strip():
            continue
        cve_id = str(record.get("cve_id") or "unknown").strip() or "unknown"
        fragment_dir.mkdir(parents=True, exist_ok=True)
        fragment_path = fragment_dir / f"{_safe_file_stem(cve_id)}.config.fragment"
        fragment_path.write_text(fragment, encoding="utf-8")
        record["minimal_config_fragment_path"] = str(fragment_path)
        record["minimal_config_profile"] = {
            "status": "fragment_ready",
            "fragment_path": str(fragment_path),
            "merge_config_cmd": f"./scripts/kconfig/merge_config.sh .config {fragment_path}",
            "olddefconfig_cmd": "make olddefconfig",
            "reason": "高分候选遇到 feature_not_enabled 时可用该 fragment 准备正向验证 profile",
        }
        written.append(cve_id)
    return written


def prepare_stable_baselines_for_records(*, records: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    """full run 前按 stable_source_baseline_ref 显式准备未修复源码基线"""

    if not args.prepare_stable_baseline:
        for record in records:
            record["stable_baseline_preparation"] = {
                "status": "disabled",
                "reason": "已通过 --no-prepare-stable-baseline 关闭自动准备",
            }
        return records

    for record in records:
        baseline_ref = str(record.get("stable_source_baseline_ref") or "").strip()
        if not baseline_ref:
            record["stable_baseline_preparation"] = {
                "status": "skipped",
                "reason": "分析产物未提供 stable_source_baseline_ref",
            }
            continue
        if args.only_positive_candidates and not record.get("positive_pool_candidate"):
            record["stable_baseline_preparation"] = {
                "status": "skipped",
                "baseline_ref": baseline_ref,
                "reason": "当前样例未进入 positive_pool_candidate，本轮不消耗 baseline 准备时间",
            }
            continue
        try:
            prepare_args = ["prepare-stable-baseline", "--baseline-ref", baseline_ref]
            stable_source_git_dir = getattr(args, "stable_source_git_dir", None)
            stable_source_cache_dir = getattr(args, "stable_source_cache_dir", None)
            stable_config_source = getattr(args, "stable_config_source", None)
            if stable_source_git_dir is not None:
                prepare_args.extend(["--stable-git-dir", str(stable_source_git_dir)])
            if stable_source_cache_dir is not None:
                prepare_args.extend(["--output-root", str(stable_source_cache_dir)])
            if stable_config_source is not None:
                prepare_args.extend(["--config-source", str(stable_config_source)])
            prepare_args.extend(["--no-write-build-config", "--json"])
            payload = run_cli_json(
                python_bin=args.python,
                cwd=PROJECT_ROOT,
                cli_args=prepare_args,
                timeout_sec=args.stable_baseline_timeout_sec,
            )
        except Exception as exc:
            record.update(
                {
                    "stable_baseline_preparation": {
                        "status": "failed",
                        "baseline_ref": baseline_ref,
                        "error": str(exc)[:2000],
                    },
                    "stable_baseline_ready": False,
                    "stable_bucket_ready": False,
                    "positive_pool_candidate": False,
                    "sample_bucket": None,
                    "acceptance_role": "development_sample",
                    "screening_tier": "blocked_by_stable_baseline_prepare_failed",
                    "reason": "stable source baseline 自动准备失败，先处理源码基线环境",
                    "agent_next_action": "inspect_stable_source_baseline_failure",
                }
            )
            continue
        record["stable_baseline_preparation"] = {
            "status": "prepared",
            "baseline_ref": baseline_ref,
            "output_dir": payload.get("output_dir"),
            "reused_existing": payload.get("reused_existing", False),
            "git_head": payload.get("git_head"),
            "config_path": payload.get("config_path"),
        }
        record["stable_kernel_src_dir"] = payload.get("output_dir")
        record["stable_baseline_ready"] = True
    return records


def _safe_file_stem(value: str) -> str:
    """生成跨平台安全文件名"""

    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
    return safe.strip("_") or "unknown"


def _select_target_inference_source(build_config: Any) -> Path | None:
    """选择用于构建目标推导的源码树"""

    for attr in [
        "clean_kernel_src_dir",
        "vendor_kernel_src_dir",
        "prepared_kernel_src_dir",
        "kernel_src_dir",
        "stable_kernel_src_dir",
        "kernel_devel_dir",
    ]:
        raw_path = str(getattr(build_config, attr, "") or "").strip()
        if not raw_path:
            continue
        path = Path(raw_path)
        if (path / "Makefile").exists():
            return path
    return None


def infer_build_targets_for_record(
    *,
    orchestrator: BuildOrchestrator,
    source_dir: Path | None,
    config_values: dict[str, str],
    target_files: list[Path],
) -> list[dict[str, str]]:
    """把一个样例的 target_files 转成构建目标说明"""

    if source_dir is None:
        return [{"file": str(path), "target": "unknown", "state": "source_missing"} for path in target_files]

    target_infos: list[dict[str, str]] = []
    for relative_path in target_files:
        target, state = orchestrator._resolve_build_target_detail(
            source_dir=source_dir,
            relative_path=relative_path,
            config_values=config_values,
        )
        target_infos.append(
            {
                "file": relative_path.as_posix(),
                "target": target or "vmlinux",
                "state": state,
            }
        )
    return target_infos


def latest_attempt_dir(*, workspace_root: Path, task_id: str) -> Path:
    """返回当前任务最新 attempt 目录"""

    attempts_root = workspace_root / task_id / "attempts"
    if not attempts_root.exists():
        return attempts_root / "001"
    candidates = [path for path in attempts_root.iterdir() if path.is_dir() and path.name.isdigit()]
    if not candidates:
        return attempts_root / "001"
    return sorted(candidates, key=lambda path: int(path.name))[-1]


def read_json_if_exists(path: Path) -> dict[str, Any] | None:
    """按需读取 JSON 文件"""

    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_module_path(raw_path: str | None, *, attempt_dir: Path) -> Path | None:
    """解析 build_summary 中记录的模块路径，缺失时在 attempt 目录兜底查找"""

    if raw_path:
        path = Path(raw_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path

    candidates = sorted(attempt_dir.rglob("*.ko"))
    return candidates[0] if candidates else None


def read_module_vermagic(module_path: Path | None) -> str | None:
    """读取 livepatch 模块的 vermagic，作为正向验收的内核版本证据"""

    if module_path is None or not module_path.exists():
        return None
    try:
        proc = subprocess.run(
            ["modinfo", "-F", "vermagic", str(module_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def positive_acceptance_evidence_ok(item: dict[str, Any]) -> bool:
    """判断一条结果是否满足正向池写入门槛"""

    if item.get("screening_tier") != "positive_acceptance_confirmed":
        return False
    if item.get("sample_bucket") == "kpatch_constraint" or item.get("known_pool_hit") == "kpatch_constraint_pool":
        return False
    blocked_failures = {"kpatch_constraint", "kpatch_constraint_unresolved", "unfixable_by_livepatch"}
    if str(item.get("failure_type") or item.get("run_failure_type") or "") in blocked_failures:
        return False
    if item.get("build_status") != "built" or item.get("validation_status") != "passed":
        return False
    if not item.get("module_path") or item.get("module_exists") is False:
        return False
    module_vermagic = str(item.get("module_vermagic") or "").strip()
    target_kernel = str(item.get("target_kernel_release") or item.get("target_kernel") or "").strip()
    if not module_vermagic:
        return False
    return not target_kernel or target_kernel in module_vermagic


def count_existing_positive_pool(fixture_path: Path) -> int:
    """统计当前正向池已有样例数"""

    if not fixture_path.exists():
        return 0
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return 0
    return len({str(item.get("cve_id")) for item in payload if isinstance(item, dict) and item.get("cve_id")})


def summarize(results: list[dict[str, Any]], *, positive_pool_fixture: Path, positive_pool_target: int) -> dict[str, Any]:
    """汇总筛选结果"""

    bucket_counter = Counter(item.get("sample_bucket") or "unbucketed" for item in results)
    tier_counter = Counter(item.get("screening_tier") or "unknown" for item in results)
    role_counter = Counter(item.get("acceptance_role") or "unknown" for item in results)
    current_positive_pool_size = count_existing_positive_pool(positive_pool_fixture)
    confirmed_positive = [item["cve_id"] for item in results if positive_acceptance_evidence_ok(item)]
    executed_records = [
        item
        for item in results
        if item.get("run_attempts") or item.get("run_status") or item.get("build_status") or item.get("validation_status")
    ]
    attempt_counts = [
        len(item.get("run_attempts") or []) or int(item.get("run_index") or 1)
        for item in executed_records
    ]
    representative_total = len(executed_records) or len(results)
    representative_success_rate = (
        round(len(confirmed_positive) / representative_total, 4)
        if representative_total
        else 0.0
    )
    average_attempts = round(sum(attempt_counts) / len(attempt_counts), 2) if attempt_counts else 0.0
    projected_positive_pool_size = current_positive_pool_size + len(
        {cve for cve in confirmed_positive if cve not in {item.get("cve_id") for item in _read_positive_pool_items(positive_pool_fixture)}}
    )
    return {
        "total_cases": len(results),
        "representative_total": representative_total,
        "representative_success_rate": representative_success_rate,
        "average_attempts": average_attempts,
        "bucket_counts": dict(bucket_counter),
        "tier_counts": dict(tier_counter),
        "role_counts": dict(role_counter),
        "livepatchability_tier_counts": dict(
            Counter(str(item.get("livepatchability_tier") or "unknown") for item in results)
        ),
        "livepatchability_high": [
            item["cve_id"] for item in results if item.get("livepatchability_tier") == "high"
        ],
        "confirmed_positive_acceptance": confirmed_positive,
        "positive_pool_candidates": [
            item["cve_id"] for item in results if item.get("positive_pool_candidate")
        ],
        "stable_bucket_ready": [
            item["cve_id"] for item in results if item.get("stable_bucket_ready")
        ],
        "rag_seed_hits": [
            item["cve_id"] for item in results if item.get("rag_seed_hit")
        ],
        "known_pool_skipped": [
            item["cve_id"] for item in results if item.get("known_pool_hit")
        ],
        "stable_source_alignment_required": [
            item["cve_id"] for item in results if item.get("stable_source_alignment_required")
        ],
        "stable_baseline_prepared": [
            item["cve_id"]
            for item in results
            if (item.get("stable_baseline_preparation") or {}).get("status") == "prepared"
        ],
        "minimal_config_fragments": [
            item["cve_id"] for item in results if item.get("minimal_config_fragment_path")
        ],
        "rag_subsystem_counts": dict(Counter(str(item.get("rag_subsystem") or "unknown") for item in results if item.get("rag_seed_hit"))),
        "positive_pool_target": positive_pool_target,
        "current_positive_pool_size": current_positive_pool_size,
        "projected_positive_pool_size": projected_positive_pool_size,
        "positive_pool_gap": max(0, positive_pool_target - projected_positive_pool_size),
    }


def _read_positive_pool_items(fixture_path: Path) -> list[dict[str, Any]]:
    """读取正向池 fixture 原始条目"""

    if not fixture_path.exists():
        return []
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []


def capture_failure_context(*, workspace_root: Path, task_id: str) -> dict[str, Any]:
    """抓取 run 失败或超时时的现场信息"""

    attempt_dir = latest_attempt_dir(workspace_root=workspace_root, task_id=task_id)
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
        try:
            create_args = [
                "create",
                "--cve",
                cve_id,
                "--profile",
                args.profile,
                "--task-id",
                task_id,
                "--force-new",
                "--json",
            ]
            if args.max_attempts is not None:
                create_args[5:5] = ["--max-attempts", str(args.max_attempts)]
            create_payload = run_cli_json(
                python_bin=args.python,
                cwd=PROJECT_ROOT,
                cli_args=create_args,
                timeout_sec=args.create_timeout_sec,
            )
            analyze_payload = run_cli_json(
                python_bin=args.python,
                cwd=PROJECT_ROOT,
                cli_args=["analyze", "--task", task_id, "--json"],
                timeout_sec=args.analyze_timeout_sec,
            )
            record["create_status"] = create_payload.get("status")
            record["analyze_status"] = analyze_payload.get("status")
            record.update(load_analysis_artifacts(workspace_root=paths["workspace_root"], task_id=task_id))
            record.update(classify_sample_pool_result(record))
        except Exception as exc:
            record["create_or_analyze_status"] = "error"
            record["create_or_analyze_error"] = str(exc)
            record.update(
                {
                    "sample_bucket": None,
                    "acceptance_role": "development_sample",
                    "screening_tier": "development_only_source_or_analysis_error",
                    "reason": "create/analyze 阶段未完成，先作为开发样例观察",
                    "stable_bucket_ready": False,
                    "positive_pool_candidate": False,
                }
            )
        records.append(record)
    return records


def run_full_phase(*, records: list[dict[str, Any]], args: argparse.Namespace, paths: dict[str, Path]) -> list[dict[str, Any]]:
    """逐条执行 run/report/replay，run 自动带外层超时"""

    max_run_attempts = args.max_run_attempts if args.max_run_attempts is not None else args.max_attempts
    max_run_attempts = max(1, int(max_run_attempts or 1))
    for record in records:
        if args.only_positive_candidates and not record.get("positive_pool_candidate"):
            record["run_skipped"] = "not_positive_candidate"
            continue

        task_id = str(record["task_id"])
        record["run_attempts"] = []
        for run_index in range(1, max_run_attempts + 1):
            run_snapshot: dict[str, Any] = {"run_index": run_index}
            try:
                run_payload = run_cli_json(
                    python_bin=args.python,
                    cwd=PROJECT_ROOT,
                    cli_args=["run", "--task", task_id, "--json"],
                    timeout_sec=args.run_timeout_sec,
                )
                run_snapshot.update(
                    {
                        "run_status": run_payload.get("status"),
                        "run_failure_type": run_payload.get("failure_type"),
                        "build_exec_status": run_payload.get("build_exec_status"),
                        "target_state": run_payload.get("target_state"),
                        "max_attempts_exhausted": run_payload.get("max_attempts_exhausted", False),
                    }
                )
                record.update(run_snapshot)
            except RuntimeError as exc:
                timed_out = getattr(exc, "timed_out", False)
                run_snapshot.update(
                    {
                        "run_status": "timeout" if timed_out else "error",
                        "run_failure_type": "run_timeout" if timed_out else "run_error",
                        "run_error": str(exc),
                    }
                )
                record["failure_type"] = "run_timeout" if timed_out else "run_error"
                record.update(run_snapshot)
                record["diagnostics"] = capture_failure_context(workspace_root=paths["workspace_root"], task_id=task_id)

            for command_name in ["report", "replay"]:
                try:
                    payload = run_cli_json(
                        python_bin=args.python,
                        cwd=PROJECT_ROOT,
                        cli_args=[command_name, "--task", task_id, "--json"],
                    )
                    run_snapshot[f"{command_name}_status"] = payload.get("status")
                    record[f"{command_name}_status"] = payload.get("status")
                except RuntimeError as exc:
                    run_snapshot[f"{command_name}_status"] = "error"
                    run_snapshot[f"{command_name}_error"] = str(exc)
                    record[f"{command_name}_status"] = "error"
                    record[f"{command_name}_error"] = str(exc)

            record.update(load_full_artifacts(workspace_root=paths["workspace_root"], task_id=task_id))
            if record.get("run_status") == "timeout" and not str(record.get("failure_type") or "").strip():
                record["failure_type"] = "run_timeout"
            if (record.get("run_status") in {"failed", "timeout", "error"} or record.get("failure_type")) and "diagnostics" not in record:
                record["diagnostics"] = capture_failure_context(workspace_root=paths["workspace_root"], task_id=task_id)
            record.update(classify_sample_pool_result(record))
            run_snapshot.update(
                {
                    "latest_attempt_dir": record.get("latest_attempt_dir"),
                    "failure_type": record.get("failure_type"),
                    "build_status": record.get("build_status"),
                    "validation_status": record.get("validation_status"),
                    "screening_tier": record.get("screening_tier"),
                    "sample_bucket": record.get("sample_bucket"),
                }
            )
            record["run_attempts"].append(run_snapshot)
            if not should_continue_run(record=record, run_index=run_index, max_run_attempts=max_run_attempts):
                break
    return records


def should_continue_run(*, record: dict[str, Any], run_index: int, max_run_attempts: int) -> bool:
    """判断是否还要让同一任务进入下一轮 run"""

    if run_index >= max_run_attempts:
        return False
    if record.get("screening_tier") == "positive_acceptance_confirmed":
        return False
    if record.get("max_attempts_exhausted"):
        return False
    terminal_failures = {
        "target_already_patched",
        "feature_not_enabled",
        "target_arch_mismatch",
        "build_cache_incomplete",
        "run_timeout",
    }
    failure_type = str(record.get("failure_type") or record.get("run_failure_type") or "")
    if failure_type in terminal_failures:
        return False
    return failure_type in {"compile_failed", "kpatch_constraint", "patch_apply_failed"} or record.get("run_status") in {
        "failed",
        "timeout",
        "error",
    }


def update_positive_pool_fixture(*, fixture_path: Path, results: list[dict[str, Any]], screening_round: str) -> list[str]:
    """把确认成功的样例写入正向池 fixture"""

    confirmed = [item for item in results if positive_acceptance_evidence_ok(item)]
    if not confirmed:
        return []
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict[str, Any]] = []
    if fixture_path.exists():
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            existing = payload
    seen = {str(item.get("cve_id")) for item in existing}
    added: list[str] = []
    for item in confirmed:
        cve_id = str(item["cve_id"])
        if cve_id in seen:
            continue
        existing.append(
            {
                "fixture_id": f"challenge-positive-{cve_id.lower()}",
                "cve_id": cve_id,
                "target_kernel": "6.6.102-5.2.an23.x86_64",
                "fixture_group": "regression",
                "sample_bucket": "buildable_and_should_pass",
                "screening_tier": "positive_acceptance_confirmed",
                "screening_round": screening_round,
                "expected_artifacts": [
                    "build_summary.json",
                    "validation_report.json",
                    "repair_intent.json",
                    "rewritten.patch",
                    "semantic_guard.json",
                    "report.json",
                    "patchweaver-*.ko",
                ],
                "expected_outcome": "当前验证机上应真实产出 .ko，并通过 load、unload、smoke、自检",
            }
        )
        seen.add(cve_id)
        added.append(cve_id)
    fixture_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return added


def write_markdown_report(*, report_path: Path, payload: dict[str, Any]) -> None:
    """输出人工复核用 Markdown 报告"""

    summary = payload["summary"]
    lines = [
        "# PatchWeaver Challenge 正向样例池筛选报告",
        "",
        "## 1. 执行参数",
        "",
        f"- mode: `{payload['mode']}`",
        f"- profile: `{payload['profile']}`",
        f"- task_prefix: `{payload['task_prefix']}`",
        f"- run_timeout_sec: `{payload['run_timeout_sec']}`",
        f"- only_positive_candidates: `{payload['only_positive_candidates']}`",
        f"- min_livepatchability_score: `{payload.get('min_livepatchability_score', 75)}`",
        f"- only_high_livepatchability: `{payload.get('only_high_livepatchability', False)}`",
        f"- workspace_root: `{payload['workspace_root']}`",
        "",
        "## 2. 汇总",
        "",
        f"- total_cases: `{summary['total_cases']}`",
        f"- confirmed_positive_acceptance: `{len(summary['confirmed_positive_acceptance'])}`",
        f"- positive_pool_candidates: `{len(summary['positive_pool_candidates'])}`",
        f"- stable_bucket_ready: `{len(summary['stable_bucket_ready'])}`",
        f"- current_positive_pool_size: `{summary['current_positive_pool_size']}`",
        f"- positive_pool_target: `{summary['positive_pool_target']}`",
        f"- positive_pool_gap: `{summary['positive_pool_gap']}`",
        f"- representative_success_rate: `{summary.get('representative_success_rate', 0.0):.0%}`",
        f"- average_attempts: `{summary.get('average_attempts', 0.0)}`",
        f"- rag_seed_hits: `{len(summary['rag_seed_hits'])}`",
        f"- known_pool_skipped: `{len(summary['known_pool_skipped'])}`",
        f"- stable_source_alignment_required: `{len(summary['stable_source_alignment_required'])}`",
        f"- stable_baseline_prepared: `{len(summary.get('stable_baseline_prepared') or [])}`",
        f"- minimal_config_fragments: `{len(summary.get('minimal_config_fragments') or [])}`",
        f"- livepatchability_high: `{len(summary.get('livepatchability_high') or [])}`",
        "",
        "### bucket_counts",
        "",
        *[f"- `{key}`: `{value}`" for key, value in sorted(summary["bucket_counts"].items())],
        "",
        "### livepatchability_tier_counts",
        "",
        *[f"- `{key}`: `{value}`" for key, value in sorted((summary.get("livepatchability_tier_counts") or {}).items())],
        "",
        "### rag_subsystem_counts",
        "",
        *[f"- `{key}`: `{value}`" for key, value in sorted(summary["rag_subsystem_counts"].items())],
        "",
        "## 3. 逐样例结果",
        "",
        "| CVE | task_id | livepatchability | bucket | tier | rag_subsystem | failure_type | source_alignment | agent_next_action | build | validation | reason |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in payload["results"]:
        lines.append(
            "| {cve} | `{task}` | `{livepatchability}` | `{bucket}` | `{tier}` | `{rag_subsystem}` | `{failure}` | `{source_alignment}` | `{agent_next_action}` | `{build}` | `{validation}` | {reason} |".format(
                cve=item.get("cve_id"),
                task=item.get("task_id"),
                livepatchability=f"{item.get('livepatchability_score', '')}/{item.get('livepatchability_tier', '')}".strip("/"),
                bucket=item.get("sample_bucket") or "",
                tier=item.get("screening_tier") or "",
                rag_subsystem=item.get("rag_subsystem") or "",
                failure=item.get("failure_type") or item.get("run_failure_type") or "",
                source_alignment="required" if item.get("stable_source_alignment_required") else "",
                agent_next_action=item.get("agent_next_action") or item.get("stable_source_baseline_action") or "",
                build=item.get("build_status") or "",
                validation=item.get("validation_status") or "",
                reason=str(item.get("reason") or "").replace("|", "/"),
            )
        )
    lines.extend(
        [
            "",
            "## 4. 后续动作",
            "",
            "1. 将 `positive_acceptance_confirmed` 样例加入正向池",
            "2. 对 `kpatch_constraint` 样例进入专项改写优化",
            "3. 对 `compile_failed` 样例优先查看 diagnostics 与 build.log",
        ]
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    """执行样例筛选"""

    args = parse_args()
    cves = load_cves(args)
    paths = runtime_paths(python_bin=args.python, cwd=PROJECT_ROOT)
    rag_seed_index = load_rag_seed_index(args.rag_seed_fixture)
    results = run_create_analyze_phase(cves=cves, args=args, paths=paths)
    results = annotate_with_rag_seed(results, rag_seed_index)
    should_gate_known_pools = (
        not args.include_known_pool_cases
        and (args.only_positive_candidates or args.only_module_target_candidates or args.update_positive_pool)
    )
    if should_gate_known_pools:
        results = apply_known_pool_gate(
            results,
            positive_pool_fixture=args.positive_pool_fixture,
            known_kpatch_constraint_fixture=args.known_kpatch_constraint_fixture,
        )
    if args.only_module_target_candidates:
        results = apply_module_target_gate(results, project_root=PROJECT_ROOT)
    config_fragment_dir = args.config_fragment_dir or args.output.parent / f"{args.output.stem}_config_fragments"
    minimal_config_fragments_written = write_minimal_config_fragments(
        records=results,
        fragment_dir=config_fragment_dir,
    )
    results = apply_livepatchability_gate(
        results,
        min_score=args.min_livepatchability_score,
        only_high=args.only_high_livepatchability or args.only_positive_candidates,
    )
    if args.mode == "full":
        results = prepare_stable_baselines_for_records(records=results, args=args)
        results = run_full_phase(records=results, args=args, paths=paths)
        results = annotate_with_rag_seed(results, rag_seed_index)
        results = apply_livepatchability_gate(
            results,
            min_score=args.min_livepatchability_score,
            only_high=False,
        )
    positive_pool_added: list[str] = []
    if args.update_positive_pool and args.mode == "full":
        positive_pool_added = update_positive_pool_fixture(
            fixture_path=args.positive_pool_fixture,
            results=results,
            screening_round=args.screening_round,
        )

    payload = {
        "mode": args.mode,
        "profile": args.profile,
        "task_prefix": args.task_prefix,
        "max_run_attempts": args.max_run_attempts,
        "run_timeout_sec": args.run_timeout_sec,
        "stable_baseline_timeout_sec": args.stable_baseline_timeout_sec,
        "prepare_stable_baseline": args.prepare_stable_baseline,
        "only_positive_candidates": args.only_positive_candidates,
        "positive_pool_fixture": str(args.positive_pool_fixture),
        "known_kpatch_constraint_fixture": str(args.known_kpatch_constraint_fixture),
        "include_known_pool_cases": args.include_known_pool_cases,
        "positive_pool_target": args.positive_pool_target,
        "min_livepatchability_score": args.min_livepatchability_score,
        "only_high_livepatchability": args.only_high_livepatchability,
        "rag_seed_fixture": str(args.rag_seed_fixture),
        "config_fragment_dir": str(config_fragment_dir),
        "minimal_config_fragments_written": minimal_config_fragments_written,
        "positive_pool_added": positive_pool_added,
        "project_root": str(paths["project_root"]),
        "workspace_root": str(paths["workspace_root"]),
        "summary": summarize(
            results,
            positive_pool_fixture=args.positive_pool_fixture,
            positive_pool_target=args.positive_pool_target,
        ),
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.report_md:
        write_markdown_report(report_path=args.report_md, payload=payload)
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
