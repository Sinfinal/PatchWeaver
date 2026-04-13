"""API 服务启动入口。"""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    """按环境变量启动 API 服务。"""

    host = os.getenv("PATCHWEAVER_API_HOST", "127.0.0.1")
    port = int(os.getenv("PATCHWEAVER_API_PORT", "18080"))
    reload_enabled = os.getenv("PATCHWEAVER_API_RELOAD", "0") == "1"
    uvicorn.run("patchweaver.api.app:app", host=host, port=port, reload=reload_enabled)


if __name__ == "__main__":
    main()
