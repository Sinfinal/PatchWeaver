"""PatchWeaver FastAPI 应用入口。"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from patchweaver import __version__
from patchweaver.api.routers import doctor, logs, overview, reports, rules, settings, skills, tasks
from patchweaver.api.schemas import HealthResponse
from patchweaver.config.loader import discover_project_root


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例。"""

    app = FastAPI(
        title="PatchWeaver API",
        version=__version__,
        description="PatchWeaver Web 控制台后端接口",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api_prefix = "/api/v1"
    app.include_router(overview.router, prefix=api_prefix)
    app.include_router(tasks.router, prefix=api_prefix)
    app.include_router(reports.router, prefix=api_prefix)
    app.include_router(doctor.router, prefix=api_prefix)
    app.include_router(rules.router, prefix=api_prefix)
    app.include_router(skills.router, prefix=api_prefix)
    app.include_router(logs.router, prefix=api_prefix)
    app.include_router(settings.router, prefix=api_prefix)

    @app.get("/healthz", response_model=HealthResponse)
    def healthz() -> HealthResponse:
        """返回最小健康检查结果。"""

        return HealthResponse(status="ok", version=__version__)

    @app.get("/")
    def index() -> RedirectResponse:
        """开发阶段默认跳转到接口文档。"""

        return RedirectResponse(url="/docs")

    _mount_web_dist(app)
    return app


def _mount_web_dist(app: FastAPI) -> None:
    """如果前端已经构建，则把静态资源挂到 /console。"""

    project_root = discover_project_root()
    dist_dir = (project_root / "web" / "dist").resolve()
    if not dist_dir.exists():
        return
    app.mount("/console", StaticFiles(directory=Path(dist_dir), html=True), name="console")


app = create_app()
