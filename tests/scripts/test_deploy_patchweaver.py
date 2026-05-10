from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = PROJECT_ROOT / "scripts" / "deploy_patchweaver.py"


def _run_deploy(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    assert DEPLOY_SCRIPT.exists(), (
        "scripts/deploy_patchweaver.py is expected to provide the deployment CLI"
    )

    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)

    return subprocess.run(
        [sys.executable, str(DEPLOY_SCRIPT), *args],
        cwd=PROJECT_ROOT,
        env=merged_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _json_stdout(proc: subprocess.CompletedProcess[str]) -> dict[str, object]:
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            "Expected --json to write a single JSON document to stdout; "
            f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
        ) from exc

    assert isinstance(payload, dict), payload
    return payload


def test_dry_run_json_reports_steps_and_checks_without_running_host_setup() -> None:
    proc = _run_deploy("--dry-run", "--json", "--skip-install", "--skip-doctor")

    assert proc.returncode == 0, proc.stderr
    payload = _json_stdout(proc)
    assert isinstance(payload.get("steps"), list), payload
    assert isinstance(payload.get("checks"), list), payload
    assert payload["steps"], payload


def test_target_kernel_mismatch_is_visible_in_json_output() -> None:
    target_kernel = "0.0.0-patchweaver-unit-test-mismatch"

    proc = _run_deploy(
        "--dry-run",
        "--json",
        "--skip-install",
        "--skip-doctor",
        "--target-kernel",
        target_kernel,
    )

    assert proc.returncode in {0, 1}, proc.stderr
    payload = _json_stdout(proc)
    rendered = json.dumps(payload, ensure_ascii=False).lower()
    assert target_kernel in rendered
    assert "mismatch" in rendered or "fail" in rendered or "不匹配" in rendered


def test_dry_run_json_does_not_expose_plaintext_secrets_in_command_plan() -> None:
    secret = "pw-unit-secret-do-not-print-5f1b57"

    proc = _run_deploy(
        "--dry-run",
        "--json",
        "--skip-install",
        "--skip-doctor",
        env={
            "PATCHWEAVER_BAILIAN_API_KEY": secret,
            "DASHSCOPE_API_KEY": secret,
            "PATCHWEAVER_SSH_PASSWORD": secret,
        },
    )

    assert proc.returncode == 0, proc.stderr
    payload = _json_stdout(proc)
    combined_output = proc.stdout + proc.stderr
    rendered_plan = json.dumps(payload, ensure_ascii=False)
    assert secret not in combined_output
    assert secret not in rendered_plan
