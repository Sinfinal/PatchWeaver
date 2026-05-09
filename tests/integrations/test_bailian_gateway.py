from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from patchweaver.integrations.bailian_gateway import (
    BailianGatewayConfig,
    BailianGatewayError,
    build_request,
    fc_handler,
    invoke_gateway,
    load_config,
    openapi_schema,
    operation_schema,
)


ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "scripts" / "run_bailian_gateway.py"


def test_load_config_reads_expected_env_without_revealing_key() -> None:
    config = load_config(
        {
            "PATCHWEAVER_BAILIAN_API_KEY": "secret-value",
            "PATCHWEAVER_API_BASE_URL": "https://patchweaver.example/api/",
            "PATCHWEAVER_API_TIMEOUT_SECONDS": "9",
        }
    )

    request = build_request("create", {"cve_id": "CVE-2099-0001"}, config)

    assert config.api_base_url == "https://patchweaver.example/api"
    assert config.timeout_seconds == 9
    assert config.has_api_key is True
    assert request["headers"]["Authorization"] == "Bearer ***"
    assert "secret-value" not in json.dumps(request)


def test_create_dry_run_returns_fc_mcp_request_descriptor() -> None:
    result = invoke_gateway(
        "create",
        {"cve_id": "CVE-2099-0001", "profile": "demo"},
        dry_run=True,
        config=BailianGatewayConfig(api_key=None, api_base_url="http://patchweaver.local"),
    )

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["request"]["method"] == "POST"
    assert result["request"]["url"] == "http://patchweaver.local/tasks"
    assert result["request"]["json"]["cve_id"] == "CVE-2099-0001"


def test_status_requires_task_id() -> None:
    with pytest.raises(BailianGatewayError, match="status requires payload.task_id"):
        build_request("status", {}, BailianGatewayConfig(api_key=None, api_base_url="http://patchweaver.local"))


def test_task_action_routes_match_patchweaver_api() -> None:
    config = BailianGatewayConfig(api_key="secret-" + "value", api_base_url="http://patchweaver.local")

    run_request = build_request("run", {"task_id": "pw task/1", "ignored": True}, config)
    replay_request = build_request("replay", {"task_id": "pw-123"}, config)
    agent_request = build_request("agent_decision", {"task_id": "pw-123"}, config)

    assert run_request["method"] == "POST"
    assert run_request["url"] == "http://patchweaver.local/tasks/pw%20task%2F1/run"
    assert run_request["json"] == {"ignored": True}
    assert replay_request["method"] == "GET"
    assert replay_request["url"] == "http://patchweaver.local/tasks/pw-123/replay"
    assert agent_request["url"] == "http://patchweaver.local/tasks/pw-123/agent-decision"
    assert "secret-value" not in json.dumps([run_request, replay_request, agent_request])


def test_fc_handler_defaults_to_dry_run() -> None:
    result = fc_handler({"action": "status", "payload": {"task_id": "pw-123"}})

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["action"] == "status"


def test_fc_handler_accepts_bailian_flat_task_fields() -> None:
    result = fc_handler({"action": "status", "task_id": "pw-flat-123", "dry_run": "true"})

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["request"]["url"].endswith("/tasks/pw-flat-123")


def test_fc_handler_accepts_json_string_events() -> None:
    result = fc_handler('{"action":"status","task_id":"pw-json","dry_run":"true"}')

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["request"]["url"].endswith("/tasks/pw-json")


def test_fc_handler_accepts_bytes_events() -> None:
    result = fc_handler(b'{"action":"status","task_id":"pw-bytes","dry_run":"true"}')

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["request"]["url"].endswith("/tasks/pw-bytes")


def test_fc_handler_merges_flat_create_fields_without_leaking_secrets() -> None:
    result = fc_handler(
        {
            "action": "create",
            "cve_id": "CVE-2099-0001",
            "profile": "demo",
            "max_attempts": 3,
        }
    )

    assert result["request"]["json"]["cve_id"] == "CVE-2099-0001"
    assert result["request"]["json"]["profile"] == "demo"
    assert result["request"]["json"]["max_attempts"] == 3


def test_operation_schema_exposes_agent_actions() -> None:
    schema = operation_schema()

    assert schema["input_schema"]["properties"]["action"]["enum"] == [
        "create",
        "status",
        "analyze",
        "run",
        "report",
        "replay",
        "agent_decision",
    ]
    assert schema["input_schema"]["properties"]["task_id"]["type"] == "string"
    assert schema["input_schema"]["additionalProperties"] is True
    assert "PATCHWEAVER_BAILIAN_API_KEY" in schema["environment"]
    assert schema["actions"]["agent_decision"]["path"] == "/tasks/{task_id}/agent-decision"


def test_openapi_schema_exposes_safe_gateway_operation() -> None:
    schema = openapi_schema("https://gateway.example.com/")

    operation = schema["paths"]["/gateway"]["post"]

    assert schema["servers"] == [{"url": "https://gateway.example.com"}]
    assert operation["operationId"] == "patchweaver_gateway"
    assert operation["requestBody"]["content"]["application/json"]["schema"]["properties"]["dry_run"]["default"] is True
    assert "sk-" not in json.dumps(schema)
    assert "b314B314" not in json.dumps(schema)


def test_cli_schema_prints_json() -> None:
    completed = subprocess.run(
        [sys.executable, str(CLI), "--schema"],
        check=True,
        capture_output=True,
        text=True,
    )

    parsed = json.loads(completed.stdout)

    assert parsed["name"] == "patchweaver_bailian_gateway"


def test_cli_openapi_prints_plugin_schema() -> None:
    completed = subprocess.run(
        [sys.executable, str(CLI), "--openapi", "--server-url", "https://gateway.example.com/"],
        check=True,
        capture_output=True,
        text=True,
    )

    parsed = json.loads(completed.stdout)

    assert parsed["openapi"] == "3.0.3"
    assert parsed["servers"][0]["url"] == "https://gateway.example.com"
    assert parsed["paths"]["/gateway"]["post"]["operationId"] == "patchweaver_gateway"


def test_cli_create_dry_run_uses_env_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATCHWEAVER_API_BASE_URL", "http://patchweaver.test")
    monkeypatch.setenv("PATCHWEAVER_BAILIAN_API_KEY", "secret-value")

    completed = subprocess.run(
        [
            sys.executable,
            str(CLI),
            "--action",
            "create",
            "--payload-json",
            '{"cve_id":"CVE-2099-0001"}',
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    parsed = json.loads(completed.stdout)

    assert parsed["request"]["url"] == "http://patchweaver.test/tasks"
    assert parsed["request"]["headers"]["Authorization"] == "Bearer ***"
    assert "secret-value" not in completed.stdout
