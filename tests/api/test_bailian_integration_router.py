from __future__ import annotations

from fastapi.testclient import TestClient

from patchweaver.api.app import create_app


def test_bailian_gateway_endpoint_defaults_to_safe_dry_run() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/integrations/bailian/gateway",
        json={"action": "status", "payload": {"task_id": "demo-task"}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["request"]["url"].endswith("/tasks/demo-task")


def test_bailian_gateway_endpoint_accepts_flat_form_fields() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/integrations/bailian/gateway",
        json={"action": "status", "task_id": "demo-flat-task", "dry_run": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["dry_run"] is True
    assert payload["request"]["url"].endswith("/tasks/demo-flat-task")


def test_bailian_openapi_endpoint_serves_plugin_schema() -> None:
    client = TestClient(create_app())

    response = client.get(
        "/api/v1/integrations/bailian/openapi.json",
        params={"server_url": "https://gateway.example.com/api/v1/integrations/bailian/"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["openapi"] == "3.0.3"
    assert payload["servers"] == [{"url": "https://gateway.example.com/api/v1/integrations/bailian"}]
    assert payload["paths"]["/gateway"]["post"]["operationId"] == "patchweaver_gateway"
    assert "dry_run" in payload["paths"]["/gateway"]["post"]["requestBody"]["content"]["application/json"]["schema"]["properties"]


def test_bailian_gateway_endpoint_rejects_invalid_action() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/integrations/bailian/gateway",
        json={"action": "not_a_patchweaver_action", "payload": {}, "dry_run": True},
    )

    assert response.status_code == 400
    assert "Unsupported action" in response.json()["detail"]
