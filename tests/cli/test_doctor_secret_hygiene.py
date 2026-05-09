from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from patchweaver.cli import app as cli_app
from patchweaver.config.models import ModelsConfig


def _doctor_runtime(project_root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        project_root=project_root,
        config_dir=project_root / "config",
        workspace_root=project_root / "workspaces",
        database_path=project_root / "data" / "patchweaver.db",
        manifest_dir=project_root / "data" / "manifests",
        default_kernel="6.6.102-5.2.an23.x86_64",
        max_attempts=5,
        parallel_read_limit=3,
        write_lock_scope="task",
        trace_mode="full",
        profile_name=None,
        enable_narrow_failover=False,
        enable_read_parallel=False,
        data_dir=project_root / "data",
    )


def _build_env() -> dict[str, object]:
    return {
        "backend": "local",
        "builder_cmd": "kpatch-build",
        "builder_ok": False,
        "builder_path": "",
        "selected_source_ok": False,
        "selected_source_dir": "",
        "config_ok": False,
        "config_path": "",
        "vmlinux_ok": False,
        "vmlinux_path": "",
    }


def _skill_dirs() -> SimpleNamespace:
    return SimpleNamespace(project="skills/project", shared="skills/shared", builtin="skills/builtin")


def test_doctor_payload_reports_env_key_presence_without_serializing_value(monkeypatch, tmp_path: Path) -> None:
    fake_secret = "fake-secret-value-that-must-not-appear"
    project_root = tmp_path / "project"
    runtime = _doctor_runtime(project_root)
    runtime.config_dir.mkdir(parents=True)
    runtime.manifest_dir.mkdir(parents=True)
    runtime.workspace_root.mkdir(parents=True)
    runtime.database_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PATCHWEAVER_BAILIAN_API_KEY", fake_secret)
    monkeypatch.setattr(cli_app.BuildOrchestrator, "probe_environment", lambda _: _build_env())
    monkeypatch.setattr(
        cli_app,
        "collect_machine_profile",
        lambda *_args, **_kwargs: SimpleNamespace(
            model_dump=lambda mode="json": {
                "build_target_kernel": None,
                "build_target_kernel_source": None,
                "machine_kernel": None,
                "machine_arch": None,
            }
        ),
    )

    payload = cli_app._doctor_payload(
        runtime,
        SimpleNamespace(kpatch_build_cmd="kpatch-build"),
        SimpleNamespace(file_path="data/logs/patchweaver.log", jsonl_path="data/logs/patchweaver.jsonl"),
        SimpleNamespace(
            skill_dirs=_skill_dirs(),
            require_manifest=False,
            enabled_skills=[],
            allowed_skill_tags=["contest"],
            skill_source_priority=["project"],
        ),
        SimpleNamespace(bootstrap_fragment_dirs=["prompts/system"]),
        ModelsConfig(api_key_env="PATCHWEAVER_BAILIAN_API_KEY", api_key=""),
    )

    serialized = json.dumps(payload, ensure_ascii=False)
    api_key_check = next(item for item in payload["checks"] if item["category"] == "models" and item["name"] == "api_key")
    assert api_key_check["ok"] is True
    assert "已配置" in api_key_check["detail"]
    assert fake_secret not in serialized
    assert fake_secret[:4] not in serialized


def test_doctor_payload_warns_on_config_api_key_without_printing_value(monkeypatch, tmp_path: Path) -> None:
    fake_secret = "fake-config-secret-value-that-must-not-appear"
    project_root = tmp_path / "project"
    runtime = _doctor_runtime(project_root)
    runtime.config_dir.mkdir(parents=True)
    runtime.manifest_dir.mkdir(parents=True)
    runtime.workspace_root.mkdir(parents=True)
    runtime.database_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.delenv("PATCHWEAVER_BAILIAN_API_KEY", raising=False)
    monkeypatch.setattr(cli_app.BuildOrchestrator, "probe_environment", lambda _: _build_env())
    monkeypatch.setattr(
        cli_app,
        "collect_machine_profile",
        lambda *_args, **_kwargs: SimpleNamespace(
            model_dump=lambda mode="json": {
                "build_target_kernel": None,
                "build_target_kernel_source": None,
                "machine_kernel": None,
                "machine_arch": None,
            }
        ),
    )

    payload = cli_app._doctor_payload(
        runtime,
        SimpleNamespace(kpatch_build_cmd="kpatch-build"),
        SimpleNamespace(file_path="data/logs/patchweaver.log", jsonl_path="data/logs/patchweaver.jsonl"),
        SimpleNamespace(
            skill_dirs=_skill_dirs(),
            require_manifest=False,
            enabled_skills=[],
            allowed_skill_tags=["contest"],
            skill_source_priority=["project"],
        ),
        SimpleNamespace(bootstrap_fragment_dirs=["prompts/system"]),
        ModelsConfig(api_key_env="PATCHWEAVER_BAILIAN_API_KEY", api_key=fake_secret),
    )

    serialized = json.dumps(payload, ensure_ascii=False)
    api_key_check = next(item for item in payload["checks"] if item["category"] == "models" and item["name"] == "api_key")
    assert api_key_check["ok"] is False
    assert api_key_check["status"] == "warn"
    assert "明文 api_key 回退" in api_key_check["detail"]
    assert fake_secret not in serialized
    assert fake_secret[:4] not in serialized
