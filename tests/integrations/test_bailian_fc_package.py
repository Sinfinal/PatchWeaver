from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

from patchweaver.integrations.bailian_fc_package import (
    build_bailian_fc_package,
    build_bailian_readiness_manifest,
    build_bailian_web_fc_package,
)


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


def test_build_bailian_web_fc_package_writes_http_custom_runtime_zip_without_secrets(tmp_path: Path) -> None:
    output_zip = tmp_path / "bailian_gateway_web.zip"
    manifest_path = tmp_path / "manifest.json"

    manifest = build_bailian_web_fc_package(
        output_zip=output_zip,
        manifest_output=manifest_path,
        include_generated_at=False,
    )

    assert manifest["package_type"] == "web_function"
    assert manifest["startup_command"] == "python3 server.py"
    assert manifest["plugin_path"] == "/gateway"
    assert output_zip.exists()
    with zipfile.ZipFile(output_zip) as archive:
        names = set(archive.namelist())
        assert {"server.py", "bailian_gateway.py", "openapi.json", "README.md"} <= names
        server = archive.read("server.py").decode("utf-8")
        payload = (
            server
            + archive.read("README.md").decode("utf-8")
            + archive.read("openapi.json").decode("utf-8")
        )

    assert "ThreadingHTTPServer" in server
    assert '"/gateway"' in server
    assert '"/healthz"' in server
    assert "sk-" not in payload
    assert "b314B314" not in payload
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["listen_port"] == 9000


def test_package_bailian_gateway_cli_can_build_web_package(tmp_path: Path) -> None:
    output_zip = tmp_path / "fc-web.zip"
    manifest_path = tmp_path / "fc-web.json"

    proc = subprocess.run(
        [
            sys.executable,
            "scripts/package_bailian_gateway.py",
            "--package-type",
            "web",
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
    assert "startup_command: python3 server.py" in proc.stdout


def test_build_bailian_readiness_manifest_records_non_secret_fc_contract(tmp_path: Path) -> None:
    output = tmp_path / "readiness.json"

    manifest = build_bailian_readiness_manifest(
        output_path=output,
        public_url="https://patchwe-gateway.example.fcapp.run/",
        mcp_service_id="mcp-test",
        include_generated_at=False,
    )

    payload = output.read_text(encoding="utf-8")
    assert manifest["status"] == "fc_default_domain_ready"
    assert manifest["public_url"] == "https://patchwe-gateway.example.fcapp.run"
    assert manifest["mcp_service"]["tool_name"] == "patchweaver_gateway"
    assert manifest["smoke_contract"]["required_initial_mode"] == "dry_run=true"
    assert manifest["secret_policy"]["secrets_written_to_manifest"] is False
    assert "sk-" not in payload
    assert "b314B314" not in payload


def test_package_bailian_gateway_cli_can_emit_readiness_manifest(tmp_path: Path) -> None:
    output_zip = tmp_path / "fc-web.zip"
    manifest_path = tmp_path / "fc-web.json"
    readiness_path = tmp_path / "readiness.json"

    proc = subprocess.run(
        [
            sys.executable,
            "scripts/package_bailian_gateway.py",
            "--package-type",
            "web",
            "--output-zip",
            str(output_zip),
            "--manifest-output",
            str(manifest_path),
            "--readiness-output",
            str(readiness_path),
            "--public-url",
            "https://patchwe-gateway.example.fcapp.run",
            "--mcp-service-id",
            "mcp-test",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert readiness_path.exists()
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    assert readiness["mcp_service"]["id"] == "mcp-test"
    assert "readiness status: fc_default_domain_ready" in proc.stdout
