from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from patchweaver.cli.app import app
from patchweaver.models.attempt import AttemptRecord
from patchweaver.models.task import MachineProfile, TaskContext
from patchweaver.storage.attempt_repo import AttemptRepository
from patchweaver.storage.task_repo import TaskRepository


def test_cli_create_returns_duplicate_payload_for_already_fixed_task(monkeypatch, tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    data_dir = project_root / "data"
    workspace_root = project_root / "workspaces"
    database_path = data_dir / "patchweaver.db"
    project_root.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    workspace_root.mkdir(parents=True, exist_ok=True)

    runtime = SimpleNamespace(
        project_root=project_root,
        workspace_root=workspace_root,
        database_path=database_path,
        profile_name="demo",
        max_attempts=3,
        default_kernel="fallback-kernel",
    )
    machine_profile = MachineProfile(
        machine_system="Linux",
        machine_kernel="6.6.102-5.2.an23.x86_64",
        machine_arch="x86_64",
        build_target_kernel="6.6.102-5.2.an23.x86_64",
        build_target_kernel_source="machine_kernel",
        selected_source_dir="/root/kernel-src-clean",
    )
    monkeypatch.setattr("patchweaver.cli.app._load_runtime", lambda **_: runtime)
    monkeypatch.setattr("patchweaver.cli.app.load_build_config", lambda *_: SimpleNamespace())
    monkeypatch.setattr(
        "patchweaver.cli.app.resolve_task_binding",
        lambda **_: ("6.6.102-5.2.an23.x86_64", "detected_machine", machine_profile),
    )
    monkeypatch.setattr("patchweaver.cli.app._build_run_logger", lambda *_: SimpleNamespace(info=lambda *args, **kwargs: None))

    task_repo = TaskRepository(database_path, project_root)
    task_repo.create_task(
        TaskContext(
            task_id="TASK-CLI-DUP-001",
            cve_id="CVE-2022-0185",
            target_kernel="6.6.102-5.2.an23.x86_64",
            target_kernel_source="detected_machine",
            profile_name="demo",
            status="target_state",
            current_attempt=1,
            max_attempts=3,
            workspace_dir=workspace_root / "TASK-CLI-DUP-001",
            machine_profile=machine_profile,
        )
    )
    AttemptRepository(database_path, project_root).create_attempt(
        AttemptRecord(
            task_id="TASK-CLI-DUP-001",
            attempt_no=1,
            attempt_id="TASK-CLI-DUP-001-A001",
            status="target_state",
            failure_type="target_already_patched",
            build_exec_status="not_run",
            target_state="target_already_patched",
        )
    )

    result = CliRunner().invoke(app, ["create", "--cve", "CVE-2022-0185", "--profile", "demo", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "duplicate"
    assert payload["created"] is False
    assert payload["reason"] == "target_already_patched"
    assert payload["existing_task"]["task_id"] == "TASK-CLI-DUP-001"
    assert payload["latest_attempt"]["target_state"] == "target_already_patched"
def test_cli_create_force_new_bypasses_duplicate_guard(monkeypatch, tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    data_dir = project_root / "data"
    workspace_root = project_root / "workspaces"
    database_path = data_dir / "patchweaver.db"
    project_root.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    workspace_root.mkdir(parents=True, exist_ok=True)

    runtime = SimpleNamespace(
        project_root=project_root,
        workspace_root=workspace_root,
        database_path=database_path,
        profile_name="demo",
        max_attempts=3,
        default_kernel="fallback-kernel",
    )
    machine_profile = MachineProfile(
        machine_system="Linux",
        machine_kernel="6.6.102-5.2.an23.x86_64",
        machine_arch="x86_64",
        build_target_kernel="6.6.102-5.2.an23.x86_64",
        build_target_kernel_source="machine_kernel",
        selected_source_dir="/root/kernel-src-clean",
    )
    monkeypatch.setattr("patchweaver.cli.app._load_runtime", lambda **_: runtime)
    monkeypatch.setattr("patchweaver.cli.app.load_build_config", lambda *_: SimpleNamespace())
    monkeypatch.setattr(
        "patchweaver.cli.app.resolve_task_binding",
        lambda **_: ("6.6.102-5.2.an23.x86_64", "detected_machine", machine_profile),
    )
    monkeypatch.setattr("patchweaver.cli.app._build_run_logger", lambda *_: SimpleNamespace(info=lambda *args, **kwargs: None))

    task_repo = TaskRepository(database_path, project_root)
    task_repo.create_task(
        TaskContext(
            task_id="TASK-CLI-DUP-002",
            cve_id="CVE-2024-1086",
            target_kernel="6.6.102-5.2.an23.x86_64",
            target_kernel_source="detected_machine",
            profile_name="demo",
            status="failed",
            current_attempt=1,
            max_attempts=3,
            workspace_dir=workspace_root / "TASK-CLI-DUP-002",
            machine_profile=machine_profile,
        )
    )

    result = CliRunner().invoke(app, ["create", "--cve", "CVE-2024-1086", "--profile", "demo", "--force-new", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["created"] is True
    assert payload["task"]["task_id"] != "TASK-CLI-DUP-002"
