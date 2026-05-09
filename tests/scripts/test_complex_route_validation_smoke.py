from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_complex_route_validation_smoke_runs_one_round(tmp_path: Path) -> None:
    output_path = tmp_path / "complex_route_validation_smoke.json"
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/complex_route_validation_smoke.py",
            "--rounds",
            "1",
            "--output",
            str(output_path),
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
    assert payload["total_runs"] == 5
    assert {item["case"] for item in payload["results"]} == {
        "callback",
        "shadow_variable",
        "callback_shadow",
        "state_preserving",
        "smpl_primary",
    }
    assert all(item["validation_status"] == "passed" for item in payload["results"])
    scaffold_results = [item for item in payload["results"] if item["case"] != "smpl_primary"]
    assert all(item["kernel_adapter_plan"] is True for item in scaffold_results)
    assert all(item["kernel_adapter_scaffold"] is True for item in scaffold_results)
    assert all(item["kernel_adapter_scaffold_path"].endswith("kernel_adapter_scaffold.c") for item in scaffold_results)
    smpl_result = next(item for item in payload["results"] if item["case"] == "smpl_primary")
    assert smpl_result["kernel_adapter_plan"] is False
    assert smpl_result["kernel_adapter_scaffold"] is False
