from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_build_timeout_cleanup_smoke_runs(tmp_path: Path) -> None:
    output_path = tmp_path / "build_timeout_cleanup_smoke.json"
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/build_timeout_cleanup_smoke.py",
            "--timeout-sec",
            "1",
            "--output",
            str(output_path),
            "--cve",
            "CVE-UNIT-0001",
            "--cve",
            "CVE-UNIT-0002",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "passed"
    assert payload["total_cases"] == 2
    assert payload["passed_cases"] == 2
    assert all(item["child_cleanup_ok"] for item in payload["results"])
