"""规则、配方与 Prompt 接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from patchweaver.api.deps import ApiContext, get_api_context
from patchweaver.api.services.catalog_service import CatalogService

router = APIRouter(tags=["catalog"])


@router.get("/rules")
def get_rules(context: ApiContext = Depends(get_api_context)) -> dict:
    """返回规则库与配方目录。"""

    return CatalogService(context).list_rules()


@router.get("/recipes")
def get_recipes(context: ApiContext = Depends(get_api_context)) -> dict:
    """兼容 recipe 单独查询入口。"""

    rules = CatalogService(context).list_rules()
    return {
        "recipe_templates": rules["sections"]["recipe_templates"],
        "recipe_manifests": rules["sections"]["recipe_manifests"],
        "smpl_templates": rules["sections"]["smpl_templates"],
    }


@router.get("/prompts")
def get_prompts(context: ApiContext = Depends(get_api_context)) -> dict:
    """返回 Prompt 目录摘要。"""

    return CatalogService(context).list_prompts()
