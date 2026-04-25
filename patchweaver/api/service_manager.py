"""PatchWeaver Web/API 常驻服务管理"""

from __future__ import annotations

import json
import platform
import shlex
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_API_SERVICE_NAME = "patchweaver-web"


def systemd_available() -> bool:
    """判断当前环境是否可用 systemd"""

    return platform.system() == "Linux" and shutil.which("systemctl") is not None


def health_probe_base_url(host: str, port: int) -> str:
    """把监听地址转换成适合本机探活的 URL"""

    probe_host = host
    if host in {"0.0.0.0", "::", "[::]"}:
        probe_host = "127.0.0.1"
    return f"http://{probe_host}:{port}"


def render_systemd_unit(
    *,
    service_name: str,
    python_executable: Path,
    project_root: Path,
    host: str,
    port: int,
) -> str:
    """生成 systemd unit 内容"""

    project_root_text = project_root.as_posix()
    python_text = python_executable.as_posix()
    quoted_project_root = shlex.quote(project_root_text)
    quoted_python = shlex.quote(python_text)
    exec_start = (
        "/bin/bash -lc "
        + shlex.quote(f"cd {quoted_project_root} && exec {quoted_python} -m patchweaver.api")
    )

    lines = [
        "[Unit]",
        f"Description={service_name} service for PatchWeaver Web console",
        "After=network.target",
        "",
        "[Service]",
        "Type=simple",
        f"WorkingDirectory={project_root_text}",
        f"Environment=PATCHWEAVER_API_HOST={host}",
        f"Environment=PATCHWEAVER_API_PORT={port}",
        "Environment=PATCHWEAVER_API_RELOAD=0",
        "Environment=PYTHONUNBUFFERED=1",
        f"ExecStart={exec_start}",
        "Restart=always",
        "RestartSec=3",
        "",
        "[Install]",
        "WantedBy=multi-user.target",
        "",
    ]
    return "\n".join(lines)


def install_systemd_service(
    *,
    service_name: str,
    python_executable: Path,
    project_root: Path,
    host: str,
    port: int,
    enable: bool,
    start: bool,
) -> dict[str, Any]:
    """在 Linux 上安装并可选启用 PatchWeaver Web/API 服务"""

    if platform.system() != "Linux":
        raise RuntimeError("当前环境不是 Linux，无法安装 systemd 服务。")

    systemctl = shutil.which("systemctl")
    if not systemctl:
        raise RuntimeError("当前环境未找到 systemctl，无法安装 systemd 服务。")

    unit_path = Path("/etc/systemd/system") / f"{service_name}.service"
    unit_text = render_systemd_unit(
        service_name=service_name,
        python_executable=python_executable,
        project_root=project_root,
        host=host,
        port=port,
    )
    unit_path.write_text(unit_text, encoding="utf-8")

    subprocess.run([systemctl, "daemon-reload"], check=True)
    if enable:
        subprocess.run([systemctl, "enable", service_name], check=True)
    if start:
        subprocess.run([systemctl, "restart", service_name], check=True)

    return {
        "service_name": service_name,
        "unit_path": str(unit_path),
        "host": host,
        "port": port,
        "enable": enable,
        "start": start,
        "healthz": f"{health_probe_base_url(host, port)}/healthz",
        "console": f"{health_probe_base_url(host, port)}/console/",
    }


def wait_for_api_ready(
    *,
    host: str,
    port: int,
    timeout_sec: float = 45.0,
    interval_sec: float = 0.5,
) -> dict[str, Any]:
    """等待 API 服务健康检查通过"""

    health_url = f"{health_probe_base_url(host, port)}/healthz"
    deadline = time.monotonic() + timeout_sec
    last_error: str | None = None

    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("status") == "ok":
                return {
                    "ready": True,
                    "healthz": health_url,
                    "payload": payload,
                }
            last_error = f"healthz 返回异常: {payload}"
        except Exception as exc:  # pragma: no cover - 真实探活分支
            last_error = str(exc)
        time.sleep(interval_sec)

    raise RuntimeError(f"API 服务未在 {timeout_sec} 秒内就绪：{health_url}；最后错误：{last_error}")
