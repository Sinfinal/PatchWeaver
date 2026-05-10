"""Build a small FC/MCP deployment package for the Bailian gateway."""

from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from patchweaver.integrations.bailian_gateway import openapi_schema, operation_schema


ENTRYPOINT = '''"""Aliyun Function Compute entrypoint for PatchWeaver Bailian gateway."""

from __future__ import annotations

from bailian_gateway import fc_handler


def handler(event, context):
    """Function Compute handler."""

    return fc_handler(event, context)
'''

WEB_SERVER = '''"""HTTP custom-runtime entrypoint for PatchWeaver Bailian gateway.

This file is intentionally standard-library only so it can run in Aliyun
Function Compute custom runtime without an extra dependency install step.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from bailian_gateway import invoke_gateway, openapi_schema


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "content-type, authorization, x-patchweaver-client")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class PatchWeaverGatewayHandler(BaseHTTPRequestHandler):
    server_version = "PatchWeaverBailianGateway/1.0"

    def do_OPTIONS(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        _json_response(self, 200, {"ok": True})

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path in ("/", "/healthz"):
            _json_response(self, 200, {"ok": True, "service": "patchweaver-bailian-gateway"})
            return
        if self.path.startswith("/openapi.json"):
            server_url = os.getenv("PATCHWEAVER_GATEWAY_PUBLIC_URL", "").rstrip("/") or "https://patchweaver-gateway.example.com"
            _json_response(self, 200, openapi_schema(server_url))
            return
        _json_response(self, 404, {"ok": False, "error": "not_found", "path": self.path})

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path not in ("/gateway", "/api/v1/integrations/bailian/gateway"):
            _json_response(self, 404, {"ok": False, "error": "not_found", "path": self.path})
            return

        try:
            length = int(self.headers.get("content-length", "0") or "0")
            raw = self.rfile.read(length) if length > 0 else b"{}"
            event = json.loads(raw.decode("utf-8") or "{}")
        except Exception as exc:  # pragma: no cover - defensive boundary for FC runtime
            _json_response(self, 400, {"ok": False, "error": f"invalid_json: {exc}"})
            return

        if not isinstance(event, dict):
            _json_response(self, 400, {"ok": False, "error": "request body must be a JSON object"})
            return

        payload = event.get("payload")
        if not isinstance(payload, dict):
            payload = {
                key: value
                for key, value in event.items()
                if key not in {"action", "dry_run", "payload"}
            }
        try:
            result = invoke_gateway(
                str(event.get("action") or "status"),
                payload,
                dry_run=bool(event.get("dry_run", True)),
            )
        except Exception as exc:  # pragma: no cover - keeps platform response structured
            _json_response(self, 500, {"ok": False, "error": str(exc)})
            return
        _json_response(self, 200, result)

    def log_message(self, format: str, *args: Any) -> None:
        # FC captures stdout/stderr; keep request logs terse and non-secret.
        print("%s - %s" % (self.address_string(), format % args))


def main() -> None:
    port = int(os.getenv("FC_SERVER_PORT") or os.getenv("PORT") or "9000")
    server = ThreadingHTTPServer(("0.0.0.0", port), PatchWeaverGatewayHandler)
    print(f"PatchWeaver Bailian gateway listening on 0.0.0.0:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
'''


README = """# PatchWeaver Bailian FC Package

This package is intentionally small and uses only Python standard library modules.

## Function Entrypoint

- File: `index.py`
- Handler: `index.handler`

## Required Environment

- `PATCHWEAVER_API_BASE_URL`: PatchWeaver API base URL reachable from FC.
- `PATCHWEAVER_BAILIAN_API_KEY`: optional bearer token. Keep it in FC secrets or protected environment variables.
- `PATCHWEAVER_API_TIMEOUT_SECONDS`: optional HTTP timeout.

## Safe Smoke Test Payload

```json
{
  "action": "status",
  "payload": {
    "task_id": "demo-task"
  },
  "dry_run": true
}
```

Keep `dry_run=true` for first console validation. Switch to `false` only after network access to PatchWeaver API is confirmed.

## OpenAPI Plugin Route

The package also includes `openapi.json` for Bailian plugin registration. If you deploy PatchWeaver API directly, the equivalent schema is available from:

```text
/api/v1/integrations/bailian/openapi.json?server_url=https://<reachable-host>/api/v1/integrations/bailian
```

The plugin operation calls:

```text
POST /api/v1/integrations/bailian/gateway
```
"""


def build_bailian_fc_package(
    *,
    output_zip: Path,
    manifest_output: Path | None = None,
    include_generated_at: bool = True,
) -> dict[str, Any]:
    """Build a deployable FC package for the Bailian gateway."""

    gateway_source = Path(__file__).with_name("bailian_gateway.py")
    schema = operation_schema()
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "package": str(output_zip),
        "entrypoint": "index.handler",
        "files": ["index.py", "bailian_gateway.py", "schema.json", "openapi.json", "README.md"],
        "required_environment": [
            {"name": "PATCHWEAVER_API_BASE_URL", "required": True, "secret": False},
            {"name": "PATCHWEAVER_BAILIAN_API_KEY", "required": False, "secret": True},
            {"name": "PATCHWEAVER_API_TIMEOUT_SECONDS", "required": False, "secret": False},
        ],
        "safe_default": "dry_run=true",
        "limits": [
            "The package does not create a Bailian application by itself.",
            "A Bailian console login or cloud deployment credential is still required to publish an application link.",
            "Secret values are not read, printed, or written.",
        ],
    }
    if include_generated_at:
        manifest["generated_at"] = datetime.now(timezone.utc).isoformat()

    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("index.py", ENTRYPOINT)
        archive.write(gateway_source, "bailian_gateway.py")
        archive.writestr("schema.json", json.dumps(schema, ensure_ascii=False, indent=2) + "\n")
        archive.writestr("openapi.json", json.dumps(openapi_schema(), ensure_ascii=False, indent=2) + "\n")
        archive.writestr("README.md", README)

    if manifest_output is not None:
        manifest_output.parent.mkdir(parents=True, exist_ok=True)
        manifest_output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def build_bailian_web_fc_package(
    *,
    output_zip: Path,
    manifest_output: Path | None = None,
    include_generated_at: bool = True,
) -> dict[str, Any]:
    """Build a Function Compute custom-runtime web package.

    This package is the one to use when Bailian expects a stable HTTPS plugin
    base URL. It starts a tiny HTTP server and exposes `/gateway`.
    """

    gateway_source = Path(__file__).with_name("bailian_gateway.py")
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "package_type": "web_function",
        "package": str(output_zip),
        "runtime": "custom.debian10",
        "startup_command": "python3 server.py",
        "listen_port": 9000,
        "health_path": "/healthz",
        "plugin_path": "/gateway",
        "compat_plugin_path": "/api/v1/integrations/bailian/gateway",
        "files": ["server.py", "bailian_gateway.py", "openapi.json", "README.md"],
        "required_environment": [
            {"name": "PATCHWEAVER_API_BASE_URL", "required": True, "secret": False},
            {"name": "PATCHWEAVER_GATEWAY_PUBLIC_URL", "required": False, "secret": False},
            {"name": "PATCHWEAVER_BAILIAN_API_KEY", "required": False, "secret": True},
            {"name": "PATCHWEAVER_API_TIMEOUT_SECONDS", "required": False, "secret": False},
        ],
        "safe_default": "dry_run=true",
    }
    if include_generated_at:
        manifest["generated_at"] = datetime.now(timezone.utc).isoformat()

    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("server.py", WEB_SERVER)
        archive.write(gateway_source, "bailian_gateway.py")
        archive.writestr("openapi.json", json.dumps(openapi_schema(), ensure_ascii=False, indent=2) + "\n")
        archive.writestr("README.md", README)

    if manifest_output is not None:
        manifest_output.parent.mkdir(parents=True, exist_ok=True)
        manifest_output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def build_bailian_readiness_manifest(
    *,
    output_path: Path,
    public_url: str,
    mcp_service_name: str = "patchweaver-bailian-gateway",
    mcp_service_id: str | None = None,
    include_generated_at: bool = True,
) -> dict[str, Any]:
    """Write non-secret production-readiness evidence for the Bailian gateway.

    The manifest is intentionally declarative. It records the public endpoint and
    smoke-test contract without embedding API keys, cookies, passwords, or cloud
    deployment credentials.
    """

    clean_url = public_url.rstrip("/")
    if not clean_url.startswith(("https://", "http://")):
        raise ValueError("public_url must be an absolute http(s) URL")

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "component": "patchweaver-bailian-gateway",
        "status": "fc_default_domain_ready",
        "public_url": clean_url,
        "mcp_service": {
            "name": mcp_service_name,
            "id": mcp_service_id or "",
            "tool_name": "patchweaver_gateway",
            "tool_path": "POST /gateway",
            "compat_tool_path": "POST /api/v1/integrations/bailian/gateway",
        },
        "smoke_contract": {
            "healthz": f"{clean_url}/healthz",
            "gateway": f"{clean_url}/gateway",
            "compat_gateway": f"{clean_url}/api/v1/integrations/bailian/gateway",
            "required_initial_mode": "dry_run=true",
            "verified_actions": ["status", "agent_decision"],
        },
        "secret_policy": {
            "secrets_written_to_manifest": False,
            "required_secret_storage": "Function Compute protected environment variables or secret manager",
            "forbidden_fields": ["api_key", "password", "cookie", "token"],
        },
        "delivery_boundary": [
            "The fcapp.run default HTTPS domain is acceptable for controlled smoke tests.",
            "Bind a custom domain, API Gateway, or ALB if the final external delivery requires production-grade exposure.",
            "Real task execution must stay behind authentication and timeout controls; first-party smoke tests should keep dry_run=true.",
        ],
    }
    if include_generated_at:
        manifest["generated_at"] = datetime.now(timezone.utc).isoformat()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest
