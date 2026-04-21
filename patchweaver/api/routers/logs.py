"""日志接口"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from patchweaver.api.deps import ApiContext, get_api_context
from patchweaver.api.services.log_service import LogService

router = APIRouter(tags=["logs"])


@router.get("/logs")
def get_logs(limit: int = Query(default=120, ge=20, le=400), context: ApiContext = Depends(get_api_context)) -> dict:
    """返回系统日志与最近构建日志"""

    return LogService(context).tail_logs(limit=limit)


@router.get("/logs/tail")
def tail_logs(limit: int = Query(default=120, ge=20, le=400), context: ApiContext = Depends(get_api_context)) -> dict:
    """兼容文档里的 logs tail 路径"""

    return LogService(context).tail_logs(limit=limit)
