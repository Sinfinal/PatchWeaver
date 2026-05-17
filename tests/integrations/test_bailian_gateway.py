from __future__ import annotations

from patchweaver.integrations.bailian_gateway import (
    SUPPORTED_ACTIONS,
    BailianGatewayConfig,
    build_request,
    normalize_bailian_payload,
    openapi_schema,
    operation_schema,
)


def _config() -> BailianGatewayConfig:
    return BailianGatewayConfig(
        api_key="secret-token",
        api_base_url="http://127.0.0.1:18084/api/v1",
        timeout_seconds=30,
    )


def test_supported_actions_include_rag_operations() -> None:
    for action in ("rag_search", "rag_health", "rag_stats", "rag_import_status", "rag_reindex"):
        assert action in SUPPORTED_ACTIONS


def test_build_request_maps_rag_search_to_api_route() -> None:
    request = build_request(
        "rag_search",
        {"query": "CVE-2024-1086 netfilter verdict", "limit": 3, "subsystem": "net"},
        _config(),
    )

    assert request["method"] == "POST"
    assert request["url"] == "http://127.0.0.1:18084/api/v1/rag/search"
    assert request["json"] == {
        "query": "CVE-2024-1086 netfilter verdict",
        "limit": 3,
        "subsystem": "net",
    }


def test_build_request_maps_rag_health_to_api_route() -> None:
    request = build_request("rag_health", {}, _config())

    assert request["method"] == "GET"
    assert request["url"] == "http://127.0.0.1:18084/api/v1/rag/health"
    assert request["json"] is None


def test_normalize_bailian_payload_accepts_rag_flat_fields() -> None:
    payload = normalize_bailian_payload(
        {
            "action": "rag_search",
            "query": "CVE-2024-1086 netfilter verdict",
            "limit": 2,
            "subsystem": "net",
            "payload": {},
        }
    )

    assert payload == {
        "query": "CVE-2024-1086 netfilter verdict",
        "limit": 2,
        "subsystem": "net",
    }


def test_operation_schema_exposes_rag_actions() -> None:
    schema = operation_schema()
    actions = schema["actions"]
    properties = schema["input_schema"]["properties"]

    assert "rag_search" in actions
    assert actions["rag_search"]["path"] == "/rag/search"
    assert "rag_health" in actions
    assert "query" in properties
    assert "subsystem" in properties


def test_openapi_schema_contains_rag_example() -> None:
    schema = openapi_schema("https://example.com/api/v1/integrations/bailian")
    examples = (
        schema["paths"]["/gateway"]["post"]["requestBody"]["content"]["application/json"]["examples"]
    )

    assert "ragSearch" in examples
    assert examples["ragSearch"]["value"]["action"] == "rag_search"
