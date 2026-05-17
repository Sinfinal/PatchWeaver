"""Bailian/Function Compute/MCP gateway adapter for PatchWeaver.

The gateway keeps Bailian integration deliberately thin: it exposes a stable
tool contract and forwards calls to the existing PatchWeaver API. Secrets are
read from environment variables only and are always redacted in dry-run output.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping


SUPPORTED_ACTIONS = (
    "create",
    "status",
    "analyze",
    "run",
    "report",
    "replay",
    "agent_decision",
    "rag_search",
    "rag_health",
    "rag_stats",
    "rag_import_status",
    "rag_reindex",
)
DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class BailianGatewayConfig:
    """Runtime config for the Bailian gateway."""

    api_key: str | None
    api_base_url: str
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key)


class BailianGatewayError(RuntimeError):
    """Raised when a gateway request cannot be built or completed."""


def load_config(env: Mapping[str, str] | None = None) -> BailianGatewayConfig:
    """Load gateway config without exposing secret values."""

    source = os.environ if env is None else env
    timeout_value = source.get("PATCHWEAVER_API_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))
    try:
        timeout_seconds = max(1, int(timeout_value))
    except ValueError:
        timeout_seconds = DEFAULT_TIMEOUT_SECONDS
    return BailianGatewayConfig(
        api_key=source.get("PATCHWEAVER_BAILIAN_API_KEY"),
        api_base_url=source.get("PATCHWEAVER_API_BASE_URL", DEFAULT_API_BASE_URL).rstrip("/"),
        timeout_seconds=timeout_seconds,
    )


def operation_schema() -> dict[str, Any]:
    """Return the FC/MCP-facing tool schema."""

    return {
        "name": "patchweaver_bailian_gateway",
        "description": (
            "Create PatchWeaver tasks, trigger analyze/run/report/replay, inspect "
            "Agent decisions, and query PatchWeaver RAG through Bailian Function Compute or MCP tools."
        ),
        "environment": {
            "PATCHWEAVER_BAILIAN_API_KEY": "Optional bearer token for PatchWeaver API calls. Value must stay secret.",
            "PATCHWEAVER_API_BASE_URL": f"PatchWeaver API base URL. Defaults to {DEFAULT_API_BASE_URL}.",
            "PATCHWEAVER_API_TIMEOUT_SECONDS": f"HTTP timeout. Defaults to {DEFAULT_TIMEOUT_SECONDS}.",
        },
        "input_schema": {
            "type": "object",
            "required": ["action"],
            "properties": {
                "action": {"type": "string", "enum": list(SUPPORTED_ACTIONS)},
                "payload": {
                    "type": "object",
                    "description": "Action-specific PatchWeaver request payload.",
                    "default": {},
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Return invocation metadata without calling PatchWeaver.",
                    "default": True,
                },
                "task_id": {
                    "type": "string",
                    "description": "Convenience top-level task id for Bailian form-style tool calls.",
                },
                "cve_id": {
                    "type": "string",
                    "description": "Convenience top-level CVE id for create calls.",
                },
                "profile": {
                    "type": "string",
                    "description": "Optional PatchWeaver run profile for create calls.",
                },
                "target_kernel": {
                    "type": "string",
                    "description": "Optional target kernel release for create calls.",
                },
                "max_attempts": {
                    "type": "integer",
                    "description": "Optional maximum Agent attempts for create/run calls.",
                },
                "query": {
                    "type": "string",
                    "description": "RAG search query for rag_search.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Optional result limit for rag_search.",
                },
                "subsystem": {
                    "type": "string",
                    "description": "Optional subsystem filter for rag_search.",
                },
                "corpus_path": {
                    "type": "string",
                    "description": "Optional corpus path for rag_reindex.",
                },
                "drop_existing": {
                    "type": "boolean",
                    "description": "Whether rag_reindex should rebuild the existing collection.",
                },
            },
            "additionalProperties": True,
        },
        "actions": {
            "create": {
                "method": "POST",
                "path": "/tasks",
                "payload_hint": {
                    "cve_id": "CVE-2024-26742",
                    "target_kernel": "6.6.102-5.2.an23.x86_64",
                    "profile": "demo",
                    "max_attempts": 5,
                },
            },
            "status": {"method": "GET", "path": "/tasks/{task_id}", "payload_hint": {"task_id": "string"}},
            "analyze": {"method": "POST", "path": "/tasks/{task_id}/analyze", "payload_hint": {"task_id": "string"}},
            "run": {"method": "POST", "path": "/tasks/{task_id}/run", "payload_hint": {"task_id": "string"}},
            "report": {"method": "POST", "path": "/tasks/{task_id}/report", "payload_hint": {"task_id": "string"}},
            "replay": {"method": "GET", "path": "/tasks/{task_id}/replay", "payload_hint": {"task_id": "string"}},
            "agent_decision": {
                "method": "GET",
                "path": "/tasks/{task_id}/agent-decision",
                "payload_hint": {"task_id": "string"},
            },
            "rag_search": {
                "method": "POST",
                "path": "/rag/search",
                "payload_hint": {
                    "query": "CVE-2024-1086 netfilter verdict init double free fix",
                    "limit": 3,
                    "subsystem": "net",
                },
            },
            "rag_health": {"method": "GET", "path": "/rag/health", "payload_hint": {}},
            "rag_stats": {"method": "GET", "path": "/rag/stats", "payload_hint": {}},
            "rag_import_status": {"method": "GET", "path": "/rag/import-status", "payload_hint": {}},
            "rag_reindex": {
                "method": "POST",
                "path": "/rag/reindex",
                "payload_hint": {
                    "corpus_path": "rag_corpus_batch200/chunks/all_chunks.jsonl",
                    "drop_existing": True,
                },
            },
        },
        "output_schema": {
            "type": "object",
            "required": ["ok", "action"],
            "properties": {
                "ok": {"type": "boolean"},
                "action": {"type": "string"},
                "dry_run": {"type": "boolean"},
                "request": {"type": "object"},
                "response": {"type": "object"},
                "error": {"type": "string"},
            },
        },
    }


def openapi_schema(server_url: str = "https://patchweaver-gateway.example.com") -> dict[str, Any]:
    """Return a minimal OpenAPI document for Bailian plugin registration.

    The document intentionally exposes one gateway operation. PatchWeaver keeps
    the real routing inside Harness/API instead of duplicating stateful stage
    logic in the platform integration layer.
    """

    clean_server_url = server_url.rstrip("/") or "https://patchweaver-gateway.example.com"
    schema = operation_schema()
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "PatchWeaver Bailian Gateway",
            "version": "1.0.0",
            "description": (
                "Gateway for PatchWeaver hotpatch Agent operations. "
                "Build success is only valid after .ko generation and dynamic validation."
            ),
        },
        "servers": [{"url": clean_server_url}],
        "paths": {
            "/gateway": {
                "post": {
                    "operationId": "patchweaver_gateway",
                    "summary": "Invoke a PatchWeaver Agent action",
                    "description": (
                        "Create tasks, query status, run analysis/build stages, retrieve reports, "
                        "replay evidence, inspect agent decisions, or call RAG retrieval endpoints."
                    ),
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": schema["input_schema"],
                                "examples": {
                                    "safeDryRun": {
                                        "summary": "Safe first platform smoke test",
                                        "value": {
                                            "action": "status",
                                            "payload": {"task_id": "demo-task"},
                                            "dry_run": True,
                                        },
                                    },
                                    "createTask": {
                                        "summary": "Create a PatchWeaver task",
                                        "value": {
                                            "action": "create",
                                            "payload": {
                                                "cve_id": "CVE-2024-26742",
                                                "profile": "demo",
                                            },
                                            "dry_run": True,
                                        },
                                    },
                                    "ragSearch": {
                                        "summary": "Search PatchWeaver RAG knowledge cards",
                                        "value": {
                                            "action": "rag_search",
                                            "payload": {
                                                "query": "CVE-2024-1086 netfilter verdict init double free fix",
                                                "limit": 3,
                                                "subsystem": "net",
                                            },
                                            "dry_run": True,
                                        },
                                    },
                                },
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "PatchWeaver gateway result",
                            "content": {
                                "application/json": {
                                    "schema": schema["output_schema"],
                                }
                            },
                        }
                    },
                }
            }
        },
    }


def build_request(action: str, payload: Mapping[str, Any] | None, config: BailianGatewayConfig) -> dict[str, Any]:
    """Build a redacted PatchWeaver API request descriptor."""

    normalized_payload = dict(payload or {})
    if action not in SUPPORTED_ACTIONS:
        raise BailianGatewayError(f"Unsupported action: {action}")

    if action == "create":
        return {
            "method": "POST",
            "url": f"{config.api_base_url}/tasks",
            "headers": _redacted_headers(config),
            "json": normalized_payload,
        }
    if action == "rag_search":
        return {
            "method": "POST",
            "url": f"{config.api_base_url}/rag/search",
            "headers": _redacted_headers(config),
            "json": _post_payload(normalized_payload),
        }
    if action == "rag_reindex":
        return {
            "method": "POST",
            "url": f"{config.api_base_url}/rag/reindex",
            "headers": _redacted_headers(config),
            "json": _post_payload(normalized_payload),
        }
    if action in {"rag_health", "rag_stats", "rag_import_status"}:
        route_map = {
            "rag_health": "/rag/health",
            "rag_stats": "/rag/stats",
            "rag_import_status": "/rag/import-status",
        }
        return {
            "method": "GET",
            "url": f"{config.api_base_url}{route_map[action]}",
            "headers": _redacted_headers(config),
            "json": None,
        }

    task_id = str(normalized_payload.get("task_id") or "").strip()
    if not task_id:
        raise BailianGatewayError(f"{action} requires payload.task_id")

    escaped_task_id = urllib.parse.quote(task_id, safe="")
    route_map = {
        "status": ("GET", f"/tasks/{escaped_task_id}"),
        "analyze": ("POST", f"/tasks/{escaped_task_id}/analyze"),
        "run": ("POST", f"/tasks/{escaped_task_id}/run"),
        "report": ("POST", f"/tasks/{escaped_task_id}/report"),
        "replay": ("GET", f"/tasks/{escaped_task_id}/replay"),
        "agent_decision": ("GET", f"/tasks/{escaped_task_id}/agent-decision"),
    }
    method, path = route_map[action]
    return {
        "method": method,
        "url": f"{config.api_base_url}{path}",
        "headers": _redacted_headers(config),
        "json": None if method == "GET" else _post_payload(normalized_payload),
    }


def invoke_gateway(
    action: str,
    payload: Mapping[str, Any] | None = None,
    *,
    dry_run: bool = True,
    config: BailianGatewayConfig | None = None,
) -> dict[str, Any]:
    """Invoke the Bailian gateway.

    Dry-run is the safe default for Bailian console wiring and MCP schema tests.
    Set ``dry_run=False`` only when PatchWeaver API is reachable from the runtime.
    """

    runtime_config = load_config() if config is None else config
    request = build_request(action, payload, runtime_config)
    if dry_run:
        return {
            "ok": True,
            "action": action,
            "dry_run": True,
            "request": request,
            "auth": {"configured": runtime_config.has_api_key, "scheme": "Bearer"},
        }

    return {
        "ok": True,
        "action": action,
        "dry_run": False,
        "request": request,
        "response": _send_http_request(request, runtime_config),
    }


def fc_handler(event: Mapping[str, Any] | str | bytes, context: Any = None) -> dict[str, Any]:
    """Aliyun Function Compute compatible entrypoint."""

    del context
    normalized_event = parse_fc_event(event)
    action = str(normalized_event.get("action", ""))
    payload = normalize_bailian_payload(normalized_event)
    dry_run = _coerce_bool(normalized_event.get("dry_run", True))
    return invoke_gateway(action, payload, dry_run=dry_run)


def parse_fc_event(event: Mapping[str, Any] | str | bytes) -> Mapping[str, Any]:
    """Normalize Function Compute event shapes to a JSON object."""

    if isinstance(event, bytes):
        event = event.decode("utf-8")
    if isinstance(event, str):
        try:
            parsed = json.loads(event)
        except json.JSONDecodeError as exc:
            raise BailianGatewayError("event must be a JSON object") from exc
        event = parsed
    if not isinstance(event, Mapping):
        raise BailianGatewayError("event must be a JSON object")
    return event


def normalize_bailian_payload(event: Mapping[str, Any]) -> dict[str, Any]:
    """Accept both nested JSON and Bailian form-style flat tool inputs.

    Bailian's manual tool builder tends to emit flat fields such as
    ``task_id`` or ``cve_id`` instead of a nested ``payload`` object. Keeping
    this normalization here avoids duplicating adapter logic in the Agent
    prompt or in every platform-side tool definition.
    """

    payload = event.get("payload") or {}
    if not isinstance(payload, Mapping):
        raise BailianGatewayError("payload must be a JSON object")

    normalized = dict(payload)
    passthrough_keys = {
        "task_id",
        "cve_id",
        "profile",
        "target_kernel",
        "max_attempts",
        "query",
        "limit",
        "subsystem",
        "corpus_path",
        "drop_existing",
        "source_url",
        "patch_url",
        "stable_source_baseline_ref",
    }
    for key in passthrough_keys:
        value = event.get(key)
        if value not in (None, "") and key not in normalized:
            normalized[key] = value
    return normalized


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def _post_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != "task_id"}


def _redacted_headers(config: BailianGatewayConfig) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if config.has_api_key:
        headers["Authorization"] = "Bearer ***"
    return headers


def _actual_headers(config: BailianGatewayConfig) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    return headers


def _send_http_request(request: Mapping[str, Any], config: BailianGatewayConfig) -> dict[str, Any]:
    data = None
    if request.get("json") is not None:
        data = json.dumps(request["json"]).encode("utf-8")

    outbound = urllib.request.Request(
        str(request["url"]),
        data=data,
        headers=_actual_headers(config),
        method=str(request["method"]),
    )
    try:
        with urllib.request.urlopen(outbound, timeout=config.timeout_seconds) as response:
            body = response.read().decode("utf-8")
            return {
                "status": response.status,
                "body": json.loads(body) if body else {},
            }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        raise BailianGatewayError(f"PatchWeaver API returned HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise BailianGatewayError(f"PatchWeaver API request failed: {exc.reason}") from exc
