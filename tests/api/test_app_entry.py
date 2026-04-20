from __future__ import annotations

from fastapi.testclient import TestClient

from patchweaver.api import app as app_module


def test_root_redirects_to_console_when_web_dist_exists(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    (project_root / "web" / "dist").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(app_module, "discover_project_root", lambda: project_root)

    client = TestClient(app_module.create_app())
    response = client.get("/", follow_redirects=False)

    assert response.status_code in {302, 307}
    assert response.headers["location"] == "/console/"


def test_root_falls_back_to_docs_when_web_dist_missing(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(app_module, "discover_project_root", lambda: project_root)

    client = TestClient(app_module.create_app())
    response = client.get("/", follow_redirects=False)

    assert response.status_code in {302, 307}
    assert response.headers["location"] == "/docs"
