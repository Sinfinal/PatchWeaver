from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import patchweaver.runtime_inspector as runtime_inspector
from patchweaver.models.task import TaskContext
from patchweaver.runtime_inspector import collect_machine_profile, resolve_task_binding, validate_task_binding


def _patch_platform(monkeypatch, *, system: str = "Linux", release: str = "6.6.1-demo", machine: str = "x86_64") -> None:
    monkeypatch.setattr(
        runtime_inspector.platform,
        "uname",
        lambda: SimpleNamespace(system=system, release=release, machine=machine),
    )
    monkeypatch.setattr(runtime_inspector, "_detect_machine_kernel", lambda *_: release)


def test_collect_machine_profile_prefers_verified_build_env_path(monkeypatch) -> None:
    _patch_platform(monkeypatch)

    profile = collect_machine_profile(
        SimpleNamespace(),
        build_env={
            "backend": "local",
            "selected_source_dir": "/usr/src/kernels/6.6.102-5.2.an23.x86_64",
            "selected_source_ok": True,
            "config_path": "/opt/kernel-src/.config",
            "config_ok": True,
            "vmlinux_path": "/usr/lib/debug/lib/modules/5.10.0-old/vmlinux",
            "vmlinux_ok": False,
            "kernel_devel_dir": "/usr/src/kernels/5.10.0-old",
            "kernel_devel_ok": False,
        },
    )

    assert profile.build_target_kernel == "6.6.102-5.2.an23.x86_64"
    assert profile.build_target_kernel_source == "selected_source_dir"
    assert profile.machine_kernel == "6.6.1-demo"


def test_collect_machine_profile_falls_back_to_machine_kernel_when_build_env_unverified(monkeypatch) -> None:
    _patch_platform(monkeypatch, release="6.6.210-current")

    profile = collect_machine_profile(
        SimpleNamespace(),
        build_env={
            "backend": "local",
            "selected_source_dir": "/opt/kernel-src",
            "selected_source_ok": False,
            "config_path": "/opt/kernel-src/.config",
            "config_ok": False,
            "vmlinux_path": "/usr/lib/debug/lib/modules/6.6.102-5.2.an23.x86_64/vmlinux",
            "vmlinux_ok": False,
            "kernel_devel_dir": "/usr/src/kernels/6.6.102-5.2.an23.x86_64",
            "kernel_devel_ok": False,
        },
    )

    assert profile.build_target_kernel == "6.6.210-current"
    assert profile.build_target_kernel_source == "machine_kernel"


def test_resolve_task_binding_cli_override_has_highest_priority(monkeypatch) -> None:
    _patch_platform(monkeypatch, release="6.6.210-current")

    target_kernel, source, profile = resolve_task_binding(
        build_config=SimpleNamespace(),
        configured_default_kernel="fallback-kernel",
        cli_target_kernel="6.6.300-cli",
        build_env={
            "backend": "local",
            "selected_source_dir": "/usr/src/kernels/6.6.102-5.2.an23.x86_64",
            "selected_source_ok": True,
        },
    )

    assert target_kernel == "6.6.300-cli"
    assert source == "cli_override"
    assert profile.build_target_kernel == "6.6.102-5.2.an23.x86_64"


def test_validate_task_binding_reports_kernel_mismatch(monkeypatch) -> None:
    _patch_platform(monkeypatch, release="6.6.210-current")

    ok, message, profile = validate_task_binding(
        TaskContext(
            task_id="TASK-RUNTIME-001",
            cve_id="CVE-2024-1086",
            target_kernel="6.6.102-5.2.an23.x86_64",
            workspace_dir=Path("workspaces/TASK-RUNTIME-001"),
        ),
        SimpleNamespace(),
        build_env={
            "backend": "local",
            "selected_source_dir": "/usr/src/kernels/6.6.210-current",
            "selected_source_ok": True,
        },
    )

    assert ok is False
    assert "不一致" in message
    assert profile.build_target_kernel == "6.6.210-current"
