"""外部平台集成接口。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from patchweaver.integrations.bailian_gateway import BailianGatewayError, invoke_gateway, normalize_bailian_payload, openapi_schema

router = APIRouter(prefix="/integrations", tags=["integrations"])


class BailianGatewayRequest(BaseModel):
    """百炼/插件入口请求体。"""

    model_config = ConfigDict(extra="allow")

    action: str = Field(..., description="PatchWeaver action, e.g. create/status/run/report/replay/agent_decision.")
    payload: dict[str, Any] = Field(default_factory=dict, description="Action-specific payload.")
    dry_run: bool = Field(default=True, description="Safe default; return request metadata without invoking PatchWeaver.")


@router.post("/bailian/gateway")
def invoke_bailian_gateway(request: BailianGatewayRequest) -> dict[str, Any]:
    """百炼 OpenAPI 插件或 FC/MCP 网关入口。

    默认 dry-run，避免平台联调时误触发真实构建。
    """

    try:
        request_map = request.model_dump()
        return invoke_gateway(
            request.action,
            normalize_bailian_payload(request_map),
            dry_run=request.dry_run,
        )
    except BailianGatewayError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/bailian/openapi.json")
def get_bailian_openapi(
    server_url: str = Query(
        default="https://patchweaver-gateway.example.com/api/v1/integrations/bailian",
        description="Public base URL that Bailian can reach. The /gateway path is added by the schema.",
    ),
) -> dict[str, Any]:
    """返回百炼插件注册可用的 OpenAPI 文档。"""

    return openapi_schema(server_url)
