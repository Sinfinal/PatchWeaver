"""报告与评测接口"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from patchweaver.api.deps import ApiContext, get_api_context
from patchweaver.api.services.report_query_service import ReportQueryService

router = APIRouter(tags=["reports"])


@router.get("/reports/tasks/{task_id}")
def get_task_report(task_id: str, context: ApiContext = Depends(get_api_context)) -> dict:
    """返回任务级报告、回放摘要和关键产物索引"""

    try:
        return ReportQueryService(context).get_task_report(task_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/evaluations/groups")
def list_evaluation_groups(context: ApiContext = Depends(get_api_context)) -> dict:
    """返回固定样例分组清单"""

    return ReportQueryService(context).list_evaluation_groups()


@router.get("/evaluations/{group_name}/summary")
def get_group_summary(group_name: str, context: ApiContext = Depends(get_api_context)) -> dict:
    """返回固定样例分组摘要"""

    try:
        return ReportQueryService(context).get_group_summary(group_name)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/evaluations/{group_name}/fixtures/{fixture_id}")
def get_fixture_detail(group_name: str, fixture_id: str, context: ApiContext = Depends(get_api_context)) -> dict:
    """返回单个固定样例的详情摘要"""

    try:
        return ReportQueryService(context).get_fixture_detail(group_name, fixture_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
