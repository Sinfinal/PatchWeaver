from pathlib import Path

from patchweaver.cli import app as cli_app


def test_service_python_executable_preserves_virtualenv_entry(monkeypatch):
    monkeypatch.setattr(cli_app.sys, "executable", "/opt/patchweaver/.venv/bin/python")

    assert cli_app._service_python_executable() == Path("/opt/patchweaver/.venv/bin/python")
