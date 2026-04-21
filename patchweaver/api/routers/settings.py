"""设置接口"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from patchweaver.api.deps import ApiContext, get_api_context
from patchweaver.api.services.catalog_service import CatalogService

router = APIRouter(tags=["settings"])


@router.get("/settings")
def get_settings(context: ApiContext = Depends(get_api_context)) -> dict:
    """返回当前生效的主要配置"""

    return CatalogService(context).list_settings()
