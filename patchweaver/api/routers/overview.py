"""总览相关接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from patchweaver.api.deps import ApiContext, get_api_context
from patchweaver.api.services.log_service import LogService
from patchweaver.api.services.overview_service import OverviewService

router = APIRouter(tags=["overview"])


@router.get("/overview")
def get_overview(context: ApiContext = Depends(get_api_context)) -> dict:
    """返回总览页所需数据。"""

    return OverviewService(context).get_overview()


@router.get("/events")
def get_events(limit: int = 40, context: ApiContext = Depends(get_api_context)) -> dict:
    """返回近期事件流。"""

    return {"items": LogService(context).get_events(limit=limit)}
