"""Skill 接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from patchweaver.api.deps import ApiContext, get_api_context
from patchweaver.api.services.catalog_service import CatalogService

router = APIRouter(tags=["skills"])


@router.get("/skills")
def get_skills(context: ApiContext = Depends(get_api_context)) -> dict:
    """返回 Skill 清单。"""

    return CatalogService(context).list_skills()
