"""Web API 使用的请求与响应模型"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CreateTaskRequest(BaseModel):
    """创建任务时的表单参数"""

    cve_id: str
    target_kernel: str | None = None
    profile: str | None = None
    max_attempts: int | None = None
    note: str | None = None
    force_new: bool = False


class TaskActionResponse(BaseModel):
    """任务动作执行后的通用返回结构"""

    task_id: str
    status: str
    detail: dict[str, Any] = Field(default_factory=dict)


class ArtifactContentResponse(BaseModel):
    """单个产物文件的预览内容"""

    task_id: str
    relative_path: str
    project_path: str
    content: str
    content_type: str
    truncated: bool = False
    size: int | None = None


class HealthResponse(BaseModel):
    """最小健康检查结果"""

    status: str
    version: str
