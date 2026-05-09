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
