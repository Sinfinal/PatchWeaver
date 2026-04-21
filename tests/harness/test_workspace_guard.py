from __future__ import annotations

from pathlib import Path

import pytest

from patchweaver.config.resolver import resolve_workspace_root
from patchweaver.harness.workspace_guard import WorkspaceGuard
from patchweaver.models.task import TaskContext


def _task(*, workspace_dir: Path) -> TaskContext:
    return TaskContext(
        task_id="TASK-PATH-GUARD-001",
        cve_id="CVE-2024-1086",
        target_kernel="6.6.102-5.2.an23.x86_64",
        workspace_dir=workspace_dir,
    )


def test_workspace_guard_resolves_relative_task_dir_under_workspace_root(tmp_path: Path) -> None:
    project_root = tmp_path / "patchweaver"
    workspace_root = project_root / "workspaces"
    guard = WorkspaceGuard(workspace_root, project_root)

    task_dir = guard.create_task_workspace(_task(workspace_dir=Path("TASK-PATH-GUARD-001")))

    assert task_dir == (workspace_root / "TASK-PATH-GUARD-001").resolve()
    assert (task_dir / "task_context.json").exists()
    assert not (task_dir / "analysis").exists()
    assert not (task_dir / "reports").exists()
    assert not (task_dir / "attempts" / "001").exists()


def test_workspace_guard_materializes_stage_dirs_on_demand(tmp_path: Path) -> None:
    project_root = tmp_path / "patchweaver"
    workspace_root = project_root / "workspaces"
    guard = WorkspaceGuard(workspace_root, project_root)
    task_dir = guard.create_task_workspace(_task(workspace_dir=Path("TASK-PATH-GUARD-001")))

    guard.ensure_analysis_workspace(task_dir)
    guard.ensure_report_workspace(task_dir)
    attempt_dir = guard.create_attempt_workspace(task_dir, 1)

    assert (task_dir / "input").exists()
    assert (task_dir / "normalized").exists()
    assert (task_dir / "analysis" / "context").exists()
    assert (task_dir / "analysis" / "prompt").exists()
    assert (task_dir / "analysis" / "route").exists()
    assert (task_dir / "analysis" / "bootstrap").exists()
    assert (task_dir / "analysis" / "trace").exists()
    assert (task_dir / "reports" / "context").exists()
    assert (task_dir / "reports" / "prompt").exists()
    assert (task_dir / "reports" / "route").exists()
    assert attempt_dir == (task_dir / "attempts" / "001")
    assert (attempt_dir / "logs").exists()
    assert (attempt_dir / "rewrite").exists()
    assert not (attempt_dir / "bootstrap_manifest.json").exists()


def test_workspace_guard_rejects_task_dir_outside_workspace_root(tmp_path: Path) -> None:
    project_root = tmp_path / "patchweaver"
    workspace_root = project_root / "workspaces"
    guard = WorkspaceGuard(workspace_root, project_root)
    escaped_dir = tmp_path / "escaped-task"

    with pytest.raises(ValueError, match="task\\.workspace_dir"):
        guard.create_task_workspace(_task(workspace_dir=escaped_dir))


def test_resolve_workspace_root_rejects_path_outside_project_root(tmp_path: Path) -> None:
    project_root = tmp_path / "patchweaver"
    outside_workspace_root = tmp_path / "outside-workspaces"

    with pytest.raises(ValueError, match="workspace_root"):
        resolve_workspace_root(project_root, str(outside_workspace_root))
