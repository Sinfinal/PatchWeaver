from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from patchweaver.reporter.release_redaction import build_release_redaction_record
from scripts.release_redaction_check import default_scan_roots


def test_release_redaction_record_reports_missing_env_without_values(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    docs_root = project_root / "docs"
    docs_root.mkdir(parents=True)
    secret_value = "sk-" + "testnotreal1234567890"
    (docs_root / "release.md").write_text("api_" + f'key = "{secret_value}"\n', encoding="utf-8")

    record = build_release_redaction_record(
        scan_roots=[docs_root],
        project_root=project_root,
        required_env_vars=["PATCHWEAVER_BAILIAN_API_KEY"],
        environ={},
    )
    serialized = json.dumps(record, ensure_ascii=False)

    assert record["status"] == "failed"
    assert record["summary"] == {"findings": 2, "missing_env": 1}
    assert record["required_env"] == [
        {"name": "PATCHWEAVER_BAILIAN_API_KEY", "present": False, "status": "missing"}
    ]
    assert {finding["rule"] for finding in record["findings"]} == {"api_key_assignment", "dashscope_key"}
    assert secret_value not in serialized


def test_release_redaction_record_passes_with_env_and_no_plaintext_secret(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    config_root = project_root / "config"
    config_root.mkdir(parents=True)
    (config_root / "models.yaml").write_text(
        'api_key_env: "PATCHWEAVER_BAILIAN_API_KEY"\napi_key: ""\n',
        encoding="utf-8",
    )

    record = build_release_redaction_record(
        scan_roots=[config_root],
        project_root=project_root,
        required_env_vars=["PATCHWEAVER_BAILIAN_API_KEY"],
        environ={"PATCHWEAVER_BAILIAN_API_KEY": "do-not-serialize-this-value"},
    )
    serialized = json.dumps(record, ensure_ascii=False)

    assert record["status"] == "passed"
    assert record["summary"] == {"findings": 0, "missing_env": 0}
    assert record["required_env"] == [
        {"name": "PATCHWEAVER_BAILIAN_API_KEY", "present": True, "status": "present"}
    ]
    assert "do-not-serialize-this-value" not in serialized


def test_release_redaction_record_detects_platform_token_without_value(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    docs_root = project_root / "docs"
    docs_root.mkdir(parents=True)
    secret_value = "fake-platform-token-value"
    (docs_root / "delivery.md").write_text("platform_" + f'token = "{secret_value}"\n', encoding="utf-8")

    record = build_release_redaction_record(
        scan_roots=[docs_root],
        project_root=project_root,
        required_env_vars=[],
        environ={},
    )
    serialized = json.dumps(record, ensure_ascii=False)

    assert record["status"] == "failed"
    assert record["summary"] == {"findings": 1, "missing_env": 0}
    assert record["findings"][0]["rule"] == "platform_token_assignment"
    assert secret_value not in serialized


def test_release_redaction_cli_writes_safe_record(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[2]
    scan_root = tmp_path / "scan"
    scan_root.mkdir()
    secret_value = "Bearer " + "abcdefghijklmnopqrstuvwxyz123456"
    (scan_root / "notes.md").write_text(f"token: {secret_value}\n", encoding="utf-8")
    output_path = tmp_path / "release_redaction_check.json"

    result = subprocess.run(
        [
            sys.executable,
            str(project_root / "scripts" / "release_redaction_check.py"),
            "--scan-root",
            str(scan_root),
            "--required-env",
            "PATCHWEAVER_BAILIAN_API_KEY",
            "--output",
            str(output_path),
        ],
        cwd=project_root,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "secret finding count: 1" in result.stdout
    assert secret_value not in result.stdout
    payload = output_path.read_text(encoding="utf-8")
    assert secret_value not in payload
    assert json.loads(payload)["findings"][0]["rule"] == "bearer_token"


def test_release_redaction_default_roots_cover_delivery_docs() -> None:
    project_root = Path("repo").resolve()

    roots = {path.as_posix() for path in default_scan_roots(project_root)}

    assert (project_root / "README.md").as_posix() in roots
    assert (project_root / "config").as_posix() in roots
    assert (project_root / "docs").as_posix() in roots
    assert (project_root / "submission" / "docs").as_posix() in roots
    assert (project_root / "patchweaver").as_posix() in roots
    assert (project_root / "scripts").as_posix() in roots
    assert (project_root / "tests").as_posix() in roots
