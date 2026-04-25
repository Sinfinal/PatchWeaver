"""PatchWeaver FastAPI 应用入口"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from patchweaver import __version__
from patchweaver.api.routers import doctor, logs, overview, rag, reports, rules, settings, skills, tasks
from patchweaver.api.schemas import HealthResponse
from patchweaver.config.loader import discover_project_root


class SPAStaticFiles(StaticFiles):
    """Serve built assets and fall back to index.html for SPA deep links."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or _looks_like_static_asset(path):
                raise
            return await super().get_response("index.html", scope)


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例"""

    web_dist_dir = _resolve_web_dist_dir()
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
    app.include_router(rag.router, prefix=api_prefix)

    @app.get("/healthz", response_model=HealthResponse)
    def healthz() -> HealthResponse:
        """返回最小健康检查结果"""

        return HealthResponse(status="ok", version=__version__)

    @app.get("/")
    def index() -> RedirectResponse:
        """默认优先跳转到 Web 控制台；若前端未构建则回退到接口文档"""

        if web_dist_dir.exists():
            return RedirectResponse(url="/console/")
        return RedirectResponse(url="/docs")

    _mount_web_dist(app, web_dist_dir)
    return app


def _resolve_web_dist_dir() -> Path:
    """返回前端构建产物目录"""

    project_root = discover_project_root()
    return (project_root / "web" / "dist").resolve()


def _mount_web_dist(app: FastAPI, dist_dir: Path | None = None) -> None:
    """如果前端已经构建，则把静态资源挂到 /console"""

    dist_dir = dist_dir or _resolve_web_dist_dir()
    if not dist_dir.exists():
        return
    app.mount("/console", SPAStaticFiles(directory=dist_dir, html=True), name="console")


def _looks_like_static_asset(path: str) -> bool:
    """Only SPA routes should fall back to index.html; asset URLs should stay 404."""

    return "." in Path(path).name


app = create_app()
