from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

from patchweaver.integrations.bailian_fc_package import build_bailian_fc_package


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_build_bailian_fc_package_writes_deployable_zip_without_secrets(tmp_path: Path) -> None:
    output_zip = tmp_path / "bailian_gateway.zip"
    manifest_path = tmp_path / "manifest.json"

    manifest = build_bailian_fc_package(
        output_zip=output_zip,
        manifest_output=manifest_path,
        include_generated_at=False,
    )

    assert manifest["entrypoint"] == "index.handler"
    assert output_zip.exists()
    assert manifest_path.exists()
    with zipfile.ZipFile(output_zip) as archive:
        names = set(archive.namelist())
        assert {"index.py", "bailian_gateway.py", "schema.json", "openapi.json", "README.md"} <= names
        schema = json.loads(archive.read("schema.json").decode("utf-8"))
        openapi = json.loads(archive.read("openapi.json").decode("utf-8"))
        payload = (
            archive.read("README.md").decode("utf-8")
            + archive.read("schema.json").decode("utf-8")
            + archive.read("openapi.json").decode("utf-8")
        )

    assert "agent_decision" in schema["input_schema"]["properties"]["action"]["enum"]
    assert openapi["paths"]["/gateway"]["post"]["operationId"] == "patchweaver_gateway"
    assert "sk-" not in payload
    assert "b314B314" not in payload
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["safe_default"] == "dry_run=true"


def test_package_bailian_gateway_cli(tmp_path: Path) -> None:
    output_zip = tmp_path / "fc.zip"
    manifest_path = tmp_path / "fc.json"

    proc = subprocess.run(
        [
            sys.executable,
            "scripts/package_bailian_gateway.py",
            "--output-zip",
            str(output_zip),
            "--manifest-output",
            str(manifest_path),
        ],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert output_zip.exists()
    assert manifest_path.exists()
    assert "index.handler" in proc.stdout
