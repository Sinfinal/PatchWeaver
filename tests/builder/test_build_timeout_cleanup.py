from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from patchweaver.builder.orchestrator import BuildOrchestrator
from patchweaver.config.models import BuildConfig


def _write_sleepy_builder(script_path: Path) -> None:
    script_path.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "",
                "import os",
                "import subprocess",
                "import sys",
                "import time",
                "from pathlib import Path",
                "",
                "pid_file = Path(sys.argv[1])",
                "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])",
                "pid_file.write_text(str(child.pid), encoding='utf-8')",
                "print(f'child={child.pid}', flush=True)",
                "time.sleep(120)",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _pid_exists(pid: int) -> bool:
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


def _wait_until_pid_gone(pid: int) -> bool:
    for _ in range(30):
        if not _pid_exists(pid):
            return True
        time.sleep(0.1)
    return False


def test_build_timeout_cleans_child_process_tree(tmp_path: Path) -> None:
    script_path = tmp_path / "sleepy_builder.py"
    pid_file = tmp_path / "child.pid"
    _write_sleepy_builder(script_path)
    orchestrator = BuildOrchestrator(BuildConfig(build_timeout_sec=1))

    result = orchestrator._run_build_command(
        command=[sys.executable, str(script_path), str(pid_file)],
        cwd=tmp_path,
        timeout_sec=1,
    )

    assert result["timed_out"] is True
    assert result["exit_code"] == -1
    assert any("process cleanup" in line for line in result["cleanup_lines"])
    assert pid_file.exists()
    child_pid = int(pid_file.read_text(encoding="utf-8"))
    assert _wait_until_pid_gone(child_pid)
