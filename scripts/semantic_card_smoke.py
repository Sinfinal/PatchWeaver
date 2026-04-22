from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from patchweaver.analyzer.semantic_enricher import SemanticCardEnricher


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""

    parser = argparse.ArgumentParser(description="语义卡片烟测脚本")
    parser.add_argument("--cve", action="append", dest="cves", help="指定待测 CVE，可重复传入")
    parser.add_argument("--profile", default="dev", help="指定 profile")
    parser.add_argument("--max-attempts", type=int, default=1, help="指定最大尝试轮数")
    parser.add_argument("--rounds", type=int, default=5, help="连续验证轮数")
    return parser.parse_args()


def run_command(command: list[str]) -> dict[str, object]:
    """执行 CLI 命令并解析 JSON 输出"""

    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def semantic_keys(side_effects: list[str]) -> list[str]:
    """生成副作用语义键，供烟测脚本判重"""

    enricher = SemanticCardEnricher(models_config=None)
    return [enricher._semantic_item_key("must_keep_side_effects", item) for item in side_effects]


def main() -> int:
    """连续创建任务并检查副作用是否发生同义重复"""

    args = parse_args()
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    cves = args.cves or ["CVE-2022-0185"]
    total_runs = 0
    for round_no in range(1, args.rounds + 1):
        for cve_index, cve_id in enumerate(cves, start=1):
            total_runs += 1
            task_id = f"semantic-smoke-{stamp}-{round_no:02d}-{cve_index:02d}"
            create_payload = run_command(
                [
                    sys.executable,
                    "-m",
                    "patchweaver",
                    "create",
                    "--cve",
                    cve_id,
                    "--profile",
                    args.profile,
                    "--max-attempts",
                    str(args.max_attempts),
                    "--task-id",
                    task_id,
                    "--json",
                ]
            )
            analyze_payload = run_command(
                [
                    sys.executable,
                    "-m",
                    "patchweaver",
                    "analyze",
                    "--task",
                    task_id,
                    "--json",
                ]
            )

            semantic_path = PROJECT_ROOT / analyze_payload["semantic_card_path"]
            semantic_payload = json.loads(semantic_path.read_text(encoding="utf-8"))
            side_effects = semantic_payload.get("must_keep_side_effects") or []
            keys = semantic_keys(side_effects)
            if len(keys) != len(set(keys)):
                raise RuntimeError(
                    f"{task_id} 的 must_keep_side_effects 仍有同义重复: "
                    + json.dumps(side_effects, ensure_ascii=False)
                )

            print(
                json.dumps(
                    {
                        "round": round_no,
                        "task_id": task_id,
                        "cve_id": cve_id,
                        "side_effects": side_effects,
                        "semantic_keys": keys,
                        "create_status": create_payload.get("status"),
                        "analyze_status": analyze_payload.get("status"),
                    },
                    ensure_ascii=False,
                )
            )

    print(json.dumps({"status": "passed", "rounds": args.rounds, "cves": cves, "total_runs": total_runs}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
