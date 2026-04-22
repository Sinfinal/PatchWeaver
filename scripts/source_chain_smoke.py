from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from patchweaver.retriever.repair_chain import RepairChainResolver


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""

    parser = argparse.ArgumentParser(description="来源链烟测脚本")
    parser.add_argument(
        "--cve",
        action="append",
        dest="cves",
        help="指定待测 CVE，可重复传入",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=5,
        help="连续验证轮数",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "cache" / "source_fetch_smoke",
        help="烟测缓存目录",
    )
    parser.add_argument(
        "--clear-cache-each-round",
        action="store_true",
        help="每轮开始前清空缓存，确保每轮都走实时抓取",
    )
    parser.add_argument(
        "--require-stable",
        action="store_true",
        help="要求最终选中的 patch 来源必须是 linux-stable",
    )
    return parser.parse_args()


def collect_cvelist_failures(trace: dict[str, object]) -> list[dict[str, object]]:
    """筛出 cvelist 元数据阶段的失败事件"""

    failures: list[dict[str, object]] = []
    for item in trace.get("events") or []:
        if not isinstance(item, dict):
            continue
        if item.get("source_name") != "cvelistV5":
            continue
        if item.get("stage") != "metadata":
            continue
        if item.get("outcome") in {"network_error", "http_error"}:
            failures.append(item)
    return failures


def run_round(*, resolver: RepairChainResolver, cves: list[str], require_stable: bool) -> list[dict[str, object]]:
    """执行单轮来源链验证"""

    results: list[dict[str, object]] = []
    for cve_id in cves:
        payload = resolver.resolve(cve_id)
        trace = payload.get("fetch_trace") or {}
        selected = (trace.get("selected_patch_source") or {}) if isinstance(trace, dict) else {}
        failures = collect_cvelist_failures(trace if isinstance(trace, dict) else {})

        if failures:
            raise RuntimeError(f"{cve_id} 的 cvelistV5 仍出现失败事件: {json.dumps(failures, ensure_ascii=False)}")
        if require_stable and selected.get("source_name") != "linux-stable":
            raise RuntimeError(f"{cve_id} 未命中 linux-stable，当前选中来源为 {selected.get('source_name')}")

        results.append(
            {
                "cve_id": cve_id,
                "selected_source": selected.get("source_name"),
                "selected_commit": selected.get("commit_id"),
                "stable_commit": selected.get("stable_commit"),
                "upstream_commit": selected.get("upstream_commit"),
                "request_count": ((trace.get("summary") or {}) if isinstance(trace, dict) else {}).get("request_count"),
                "cache_hit_count": ((trace.get("summary") or {}) if isinstance(trace, dict) else {}).get("cache_hit_count"),
            }
        )
    return results


def main() -> int:
    """执行来源链连续烟测"""

    args = parse_args()
    cves = args.cves or ["CVE-2024-1086", "CVE-2022-0185"]
    cache_dir = args.cache_dir.resolve()
    summary: list[dict[str, object]] = []

    for round_no in range(1, args.rounds + 1):
        if args.clear_cache_each_round and cache_dir.exists():
            shutil.rmtree(cache_dir, ignore_errors=True)
        resolver = RepairChainResolver(cache_dir=cache_dir)
        round_results = run_round(
            resolver=resolver,
            cves=cves,
            require_stable=args.require_stable,
        )
        summary.append(
            {
                "round": round_no,
                "results": round_results,
            }
        )
        print(json.dumps(summary[-1], ensure_ascii=False))

    print(json.dumps({"status": "passed", "rounds": args.rounds, "cves": cves}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
