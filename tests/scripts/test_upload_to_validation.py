from __future__ import annotations

from pathlib import Path, PurePosixPath

from scripts.upload_to_validation import UploadConfig, ValidationUploader


def _config(*, clean_remote_dir: bool = True, clean_runtime_state: bool = False) -> UploadConfig:
    return UploadConfig(
        project_root=Path(__file__).resolve().parents[2],
        host="127.0.0.1",
        port=22,
        username="root",
        password="secret",
        remote_dir=PurePosixPath("/home/patchweaver/current"),
        clean_remote_dir=clean_remote_dir,
        clean_runtime_state=clean_runtime_state,
    )


def test_default_remote_cleanup_preserves_validation_artifacts() -> None:
    uploader = ValidationUploader(_config())

    commands = uploader._remote_cleanup_commands(PurePosixPath("/home/patchweaver/current"))

    joined = "\n".join(commands)
    assert "find /home/patchweaver/current" in joined
    assert "-name data" in joined
    assert "-name workspaces" in joined
    assert "rm -rf /home/patchweaver/current" not in joined


def test_runtime_state_cleanup_requires_explicit_flag() -> None:
    uploader = ValidationUploader(_config(clean_runtime_state=True))

    commands = uploader._remote_cleanup_commands(PurePosixPath("/home/patchweaver/current"))

    assert commands == ["rm -rf /home/patchweaver/current"]


def test_no_clean_disables_remote_cleanup() -> None:
    uploader = ValidationUploader(_config(clean_remote_dir=False))

    commands = uploader._remote_cleanup_commands(PurePosixPath("/home/patchweaver/current"))

    assert commands == []


def test_cli_wrapper_directly_uses_project_venv() -> None:
    uploader = ValidationUploader(_config())

    wrapper = uploader._render_remote_cli_wrapper()

    assert "run_validation_cli.sh" not in wrapper
    assert "ROOT_DIR=/home/patchweaver/current" in wrapper
    assert "cd \"$ROOT_DIR\"" in wrapper
    assert "exec /home/patchweaver/current/.venv/bin/python -m patchweaver \"$@\"" in wrapper


def test_api_launcher_uses_project_venv_and_port() -> None:
    uploader = ValidationUploader(_config())

    launcher = uploader._render_remote_api_launcher(api_port=18123)

    assert 'PATCHWEAVER_API_PORT="${PATCHWEAVER_API_PORT:-18123}"' in launcher
    assert 'exec "$ROOT_DIR/.venv/bin/python" -m patchweaver.api' in launcher
