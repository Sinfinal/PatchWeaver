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


def test_console_deep_link_falls_back_to_index_html(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    dist_dir = project_root / "web" / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    (dist_dir / "index.html").write_text("<html><body>patchweaver console</body></html>", encoding="utf-8")
    monkeypatch.setattr(app_module, "discover_project_root", lambda: project_root)

    client = TestClient(app_module.create_app())
    response = client.get("/console/tasks")

    assert response.status_code == 200
    assert "patchweaver console" in response.text


def test_console_asset_request_still_serves_static_file(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    dist_dir = project_root / "web" / "dist"
    asset_dir = dist_dir / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    (dist_dir / "index.html").write_text("<html><body>patchweaver console</body></html>", encoding="utf-8")
    (asset_dir / "app.js").write_text("console.log('ok');", encoding="utf-8")
    monkeypatch.setattr(app_module, "discover_project_root", lambda: project_root)

    client = TestClient(app_module.create_app())
    response = client.get("/console/assets/app.js")

    assert response.status_code == 200
    assert response.text == "console.log('ok');"
