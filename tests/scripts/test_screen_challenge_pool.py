from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_screen_challenge_pool_help_runs() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/screen_challenge_pool.py", "--help"],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert "Challenge 样例分层与正向样例池筛选" in proc.stdout
    assert "--run-timeout-sec" in proc.stdout
    assert "--only-positive-candidates" in proc.stdout
