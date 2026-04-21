"""API 服务启动入口。"""

from __future__ import annotations

import os

import uvicorn

from patchweaver.config.loader import discover_project_root, load_system_config


def main() -> None:
    """按环境变量启动 API 服务。"""

    default_host = "127.0.0.1"
    default_port = 18080
    try:
        project_root = discover_project_root()
        system_config = load_system_config(project_root)
        default_host = system_config.api_host
        default_port = system_config.api_port
    except Exception:
        # 独立启动时允许回退到内置默认值，避免因为配置缺失完全无法起服务。
        pass

    host = os.getenv("PATCHWEAVER_API_HOST", default_host)
    port = int(os.getenv("PATCHWEAVER_API_PORT", str(default_port)))
    reload_enabled = os.getenv("PATCHWEAVER_API_RELOAD", "0") == "1"
    uvicorn.run("patchweaver.api.app:app", host=host, port=port, reload=reload_enabled)


if __name__ == "__main__":
    main()
