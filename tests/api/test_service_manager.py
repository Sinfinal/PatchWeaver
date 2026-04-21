from pathlib import Path

from patchweaver.api import service_manager
from patchweaver.api.service_manager import health_probe_base_url, render_systemd_unit


def test_health_probe_base_url_uses_loopback_for_wildcard_host():
    assert health_probe_base_url("0.0.0.0", 18084) == "http://127.0.0.1:18084"
    assert health_probe_base_url("::", 18084) == "http://127.0.0.1:18084"


def test_health_probe_base_url_keeps_explicit_host():
    assert health_probe_base_url("10.223.185.3", 18084) == "http://10.223.185.3:18084"


def test_render_systemd_unit_contains_runtime_settings():
    unit_text = render_systemd_unit(
        service_name="patchweaver-web",
        python_executable=Path("/root/patchweaver/.venv/bin/python"),
        project_root=Path("/root/patchweaver"),
        host="0.0.0.0",
        port=18084,
    )

    assert "Description=patchweaver-web service for PatchWeaver Web console" in unit_text
    assert "Environment=PATCHWEAVER_API_HOST=0.0.0.0" in unit_text
    assert "Environment=PATCHWEAVER_API_PORT=18084" in unit_text
    assert "WorkingDirectory=/root/patchweaver" in unit_text
    assert "ExecStart=/bin/bash -lc " in unit_text
    assert "exec /root/patchweaver/.venv/bin/python -m patchweaver.api" in unit_text


def test_systemd_available_returns_true_only_on_linux_with_systemctl(monkeypatch):
    monkeypatch.setattr(service_manager.platform, "system", lambda: "Linux")
    monkeypatch.setattr(service_manager.shutil, "which", lambda name: "/bin/systemctl" if name == "systemctl" else None)
    assert service_manager.systemd_available() is True

    monkeypatch.setattr(service_manager.platform, "system", lambda: "Windows")
    assert service_manager.systemd_available() is False
