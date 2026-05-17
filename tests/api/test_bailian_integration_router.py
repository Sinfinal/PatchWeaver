from __future__ import annotations

from patchweaver.api.routers.integrations import (
    BailianGatewayRequest,
    get_bailian_openapi,
    invoke_bailian_gateway,
)
from patchweaver.api.routers import integrations as integrations_router


def test_bailian_openapi_exposes_rag_actions() -> None:
    payload = get_bailian_openapi("https://example.com/api/v1/integrations/bailian")
    action_enum = (
        payload["paths"]["/gateway"]["post"]["requestBody"]["content"]["application/json"]["schema"]["properties"][
            "action"
        ]["enum"]
    )
    assert "rag_search" in action_enum
    assert "rag_health" in action_enum


def test_bailian_gateway_accepts_flat_rag_fields(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_invoke_gateway(action: str, payload: dict[str, object], *, dry_run: bool = True):
        captured["action"] = action
        captured["payload"] = payload
        captured["dry_run"] = dry_run
        return {"ok": True, "action": action, "dry_run": dry_run, "request": {"json": payload}}

    monkeypatch.setattr(integrations_router, "invoke_gateway", _fake_invoke_gateway)
    request = BailianGatewayRequest(
        action="rag_search",
        query="CVE-2024-1086 netfilter verdict",
        limit=2,
        subsystem="net",
        dry_run=True,
    )
    response = invoke_bailian_gateway(request)

    assert captured == {
        "action": "rag_search",
        "payload": {
            "query": "CVE-2024-1086 netfilter verdict",
            "limit": 2,
            "subsystem": "net",
        },
        "dry_run": True,
    }
    assert response["ok"] is True
