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


class RagSearchRequest(BaseModel):
    """RAG 检索请求"""

    query: str
    limit: int | None = None
    cve_id: str | None = None
    subsystem: str | None = None


class RagSearchHit(BaseModel):
    """单条 RAG 命中结果"""

    chunk_id: str
    cve_id: str
    section: str
    subsystem: str | None = None
    score: float
    text: str
    card_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RagSearchResponse(BaseModel):
    """RAG 检索响应"""

    query: str
    limit: int
    collection: str
    items: list[RagSearchHit] = Field(default_factory=list)
