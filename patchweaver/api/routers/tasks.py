"""任务相关接口"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from patchweaver.api.deps import ApiContext, get_api_context
from patchweaver.api.schemas import ArtifactContentResponse, CreateTaskRequest, TaskActionResponse
from patchweaver.api.services.artifact_service import ArtifactService
from patchweaver.api.services.task_query_service import TaskQueryService

router = APIRouter(tags=["tasks"])


@router.get("/tasks")
def list_tasks(
    limit: int = Query(default=50, ge=1, le=200),
    cve_id: str | None = None,
    status: str | None = None,
    failure_type: str | None = None,
    target_kernel: str | None = None,
    build_exec_status: str | None = None,
    target_state: str | None = None,
    fixture_group: str | None = None,
    created_at_from: str | None = None,
    created_at_to: str | None = None,
    current_attempt: int | None = Query(default=None, ge=0),
    context: ApiContext = Depends(get_api_context),
) -> dict:
    """按条件读取任务列表"""

    return TaskQueryService(context).list_tasks(
        limit=limit,
        cve_id=cve_id,
        status=status,
        failure_type=failure_type,
        target_kernel=target_kernel,
        build_exec_status=build_exec_status,
        target_state=target_state,
        fixture_group=fixture_group,
        created_at_from=created_at_from,
        created_at_to=created_at_to,
        current_attempt=current_attempt,
    )


@router.post("/tasks")
def create_task(request: CreateTaskRequest, context: ApiContext = Depends(get_api_context)) -> dict:
    """创建任务并初始化工作区"""

    try:
        return TaskQueryService(context).create_task(
            cve_id=request.cve_id,
            target_kernel=request.target_kernel,
            profile=request.profile,
            max_attempts=request.max_attempts,
            note=request.note,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/tasks/{task_id}")
def get_task_detail(task_id: str, context: ApiContext = Depends(get_api_context)) -> dict:
    """读取任务详情"""

    try:
        return TaskQueryService(context).get_task_detail(task_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/tasks/{task_id}/analyze", response_model=TaskActionResponse)
def analyze_task(task_id: str, context: ApiContext = Depends(get_api_context)) -> TaskActionResponse:
    """执行分析阶段"""

    try:
        result = TaskQueryService(context).analyze_task(task_id)
        return TaskActionResponse(task_id=task_id, status="ok", detail=result)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/tasks/{task_id}/run", response_model=TaskActionResponse)
def run_task(task_id: str, context: ApiContext = Depends(get_api_context)) -> TaskActionResponse:
    """执行单轮尝试"""

    try:
        result = TaskQueryService(context).run_task(task_id)
        return TaskActionResponse(task_id=task_id, status="ok", detail=result)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/tasks/{task_id}/report", response_model=TaskActionResponse)
def report_task(task_id: str, context: ApiContext = Depends(get_api_context)) -> TaskActionResponse:
    """生成报告"""

    try:
        result = TaskQueryService(context).report_task(task_id)
        return TaskActionResponse(task_id=task_id, status="ok", detail=result)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/tasks/{task_id}/replay")
def replay_task(task_id: str, context: ApiContext = Depends(get_api_context)) -> dict:
    """返回任务最近一轮回放信息"""

    try:
        return TaskQueryService(context).replay_task(task_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/tasks/{task_id}/artifacts")
def list_artifacts(task_id: str, context: ApiContext = Depends(get_api_context)) -> dict:
    """返回任务工作区的产物树"""

    try:
        return ArtifactService(context).list_tree(task_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/tasks/{task_id}/artifacts/content", response_model=ArtifactContentResponse)
def get_artifact_content(
    task_id: str,
    path: str = Query(..., description="工作区内的相对路径"),
    context: ApiContext = Depends(get_api_context),
) -> ArtifactContentResponse:
    """读取任务产物内容"""

    try:
        payload = ArtifactService(context).read_content(task_id, path)
        return ArtifactContentResponse(**payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
