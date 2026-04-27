from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from patchweaver.builder.orchestrator import BuildOrchestrator
from patchweaver.config.models import BuildConfig


DEFAULT_CVES = [
    "CVE-2024-1086",
    "CVE-2022-0185",
    "CVE-2024-26922",
    "CVE-2023-0386",
    "CVE-2023-32233",
]


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""

    parser = argparse.ArgumentParser(description="构建超时进程组清理烟测")
    parser.add_argument("--timeout-sec", type=int, default=1, help="单个假构建命令超时时间")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "data" / "logs" / "build_timeout_cleanup_smoke.json",
        help="汇总结果输出路径",
    )
    parser.add_argument("--cve", action="append", dest="cves", help="需要验证的 CVE 标签，可重复传入")
    return parser.parse_args()


def write_sleepy_builder(script_path: Path) -> None:
    """写入会拉起子进程并故意阻塞的假构建脚本"""

    script_path.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "",
                "import subprocess",
                "import sys",
                "import time",
                "from pathlib import Path",
                "",
                "pid_file = Path(sys.argv[1])",
                "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'])",
                "pid_file.write_text(str(child.pid), encoding='utf-8')",
                "print(f'child={child.pid}', flush=True)",
                "time.sleep(300)",
                "",
            ]
        ),
        encoding="utf-8",
    )


def pid_exists(pid: int) -> bool:
    """检查进程是否仍存在"""

    if os.name == "nt":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        return str(pid) in result.stdout

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def wait_until_pid_gone(pid: int) -> bool:
    """等待子进程被系统清理"""

    for _ in range(50):
        if not pid_exists(pid):
            return True
        time.sleep(0.1)
    return False


def run_case(*, cve_id: str, workspace_root: Path, timeout_sec: int) -> dict[str, object]:
    """执行一个 CVE 标签对应的超时清理验证"""

    case_dir = workspace_root / cve_id.lower()
    case_dir.mkdir(parents=True, exist_ok=True)
    builder_script = case_dir / "fake_kpatch_build.py"
    child_pid_file = case_dir / "child.pid"
    write_sleepy_builder(builder_script)

    orchestrator = BuildOrchestrator(BuildConfig(build_timeout_sec=timeout_sec))
    result = orchestrator._run_build_command(
        command=[sys.executable, str(builder_script), str(child_pid_file)],
        cwd=case_dir,
        timeout_sec=timeout_sec,
    )
    child_pid = int(child_pid_file.read_text(encoding="utf-8")) if child_pid_file.exists() else None
    child_alive_after_cleanup = pid_exists(child_pid) if child_pid is not None else True
    child_cleanup_ok = wait_until_pid_gone(child_pid) if child_pid is not None else False
    status = "passed" if result["timed_out"] and child_cleanup_ok else "failed"
    return {
        "cve_id": cve_id,
        "status": status,
        "timed_out": result["timed_out"],
        "exit_code": result["exit_code"],
        "child_pid": child_pid,
        "child_alive_after_cleanup": child_alive_after_cleanup,
        "child_cleanup_ok": child_cleanup_ok,
        "cleanup_lines": result["cleanup_lines"],
        "stdout_excerpt": str(result["stdout"])[:500],
        "stderr_excerpt": str(result["stderr"])[:500],
    }


def main() -> int:
    """连续验证构建超时不会留下孤儿子进程"""

    args = parse_args()
    cves = args.cves or DEFAULT_CVES
    workspace_root = Path(tempfile.mkdtemp(prefix="patchweaver-build-timeout-cleanup-"))
    results = [run_case(cve_id=cve, workspace_root=workspace_root, timeout_sec=args.timeout_sec) for cve in cves]
    status = "passed" if all(item["status"] == "passed" for item in results) else "failed"
    summary = {
        "status": status,
        "total_cases": len(results),
        "passed_cases": sum(1 for item in results if item["status"] == "passed"),
        "workspace_root": str(workspace_root),
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for item in results:
        print(json.dumps(item, ensure_ascii=False))
    print(json.dumps({key: summary[key] for key in ["status", "total_cases", "passed_cases", "workspace_root"]}, ensure_ascii=False))
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
