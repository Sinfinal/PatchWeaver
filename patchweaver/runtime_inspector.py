"""运行机与构建环境探测"""

from __future__ import annotations

import platform
import re
import shlex
import shutil
import socket
import subprocess
from typing import Any

from patchweaver.builder.orchestrator import BuildOrchestrator
from patchweaver.models.task import MachineProfile, TaskContext


_PATH_KERNEL_PATTERNS = [
    re.compile(r"(?:^|[/\\])usr[/\\]src[/\\]kernels[/\\](?P<release>[^/\\]+)(?:$|[/\\])"),
    re.compile(r"(?:^|[/\\])lib[/\\]modules[/\\](?P<release>[^/\\]+)(?:$|[/\\])"),
    re.compile(r"(?:^|[/\\])linux[-_](?P<release>\d+\.\d+\.\d+[^/\\]*)(?:$|[/\\])"),
]


def collect_machine_profile(build_config: Any, *, build_env: dict[str, Any] | None = None) -> MachineProfile:
    """探测当前运行机与构建环境的关键快照"""

    snapshot = build_env or BuildOrchestrator(build_config).probe_environment()
    uname = platform.uname()
    machine_kernel = _detect_machine_kernel(uname.system, uname.release)
    build_target_kernel, build_target_source = _detect_build_target_kernel(snapshot, machine_kernel, uname.system)

    return MachineProfile(
        machine_system=uname.system or None,
        machine_kernel=machine_kernel,
        machine_arch=uname.machine or None,
        hostname=socket.gethostname() or None,
        build_target_kernel=build_target_kernel,
        build_target_kernel_source=build_target_source,
        build_backend=str(snapshot.get("backend") or "") or None,
        builder_cmd=str(snapshot.get("builder_cmd") or "") or None,
        builder_path=str(snapshot.get("builder_path") or "") or None,
        selected_source_dir=str(snapshot.get("selected_source_dir") or "") or None,
        selected_source_reason=str(snapshot.get("selected_source_reason") or "") or None,
        config_path=str(snapshot.get("config_path") or "") or None,
        vmlinux_path=str(snapshot.get("vmlinux_path") or "") or None,
    )


def resolve_task_binding(
    *,
    build_config: Any,
    configured_default_kernel: str,
    cli_target_kernel: str | None = None,
    build_env: dict[str, Any] | None = None,
) -> tuple[str, str, MachineProfile]:
    """按优先级决定任务最终绑定到的目标内核"""

    machine_profile = collect_machine_profile(build_config, build_env=build_env)
    if cli_target_kernel:
        return cli_target_kernel, "cli_override", machine_profile
    if machine_profile.build_target_kernel:
        if machine_profile.build_target_kernel_source == "machine_kernel":
            return machine_profile.build_target_kernel, "detected_machine", machine_profile
        return machine_profile.build_target_kernel, "detected_build_env", machine_profile
    return configured_default_kernel, "config_fallback", machine_profile


def validate_task_binding(task: TaskContext, build_config: Any, *, build_env: dict[str, Any] | None = None) -> tuple[bool, str, MachineProfile]:
    """校验当前运行机是否仍与任务绑定的目标内核一致"""

    machine_profile = collect_machine_profile(build_config, build_env=build_env)
    current_kernel = machine_profile.build_target_kernel
    if not current_kernel:
        return True, "当前运行机未探测到可绑定的目标内核，跳过运行前一致性校验。", machine_profile
    if current_kernel == task.target_kernel:
        return True, f"当前运行机目标内核与任务一致：{current_kernel}", machine_profile
    return (
        False,
        (
            "当前运行机探测到的目标内核与任务绑定不一致："
            f"task={task.target_kernel}，current={current_kernel}。"
            " 如需强制指定，请在创建任务时通过 --kernel 显式绑定。"
        ),
        machine_profile,
    )


def _detect_machine_kernel(system_name: str, fallback_release: str) -> str | None:
    """尽量获取当前运行机实际内核版本"""

    if system_name.lower() == "linux":
        uname_path = shutil.which("uname")
        if uname_path is not None:
            try:
                result = subprocess.run(
                    [uname_path, "-r"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                )
            except OSError:
                result = None
            if result is not None:
                detected = result.stdout.strip()
                if result.returncode == 0 and detected:
                    return detected
    return fallback_release or None


def _detect_build_target_kernel(build_env: dict[str, Any], machine_kernel: str | None, system_name: str) -> tuple[str | None, str | None]:
    """从构建环境路径中推断目标内核版本"""

    for field_name, ok_field in [
        ("selected_source_dir", "selected_source_ok"),
        ("config_path", "config_ok"),
        ("vmlinux_path", "vmlinux_ok"),
        ("kernel_devel_dir", "kernel_devel_ok"),
        ("kernel_src_dir", "kernel_src_ok"),
    ]:
        if ok_field in build_env and not build_env.get(ok_field):
            continue
        detected = _infer_kernel_from_path(build_env.get(field_name))
        if detected:
            return detected, field_name
    if system_name.lower() == "linux" and machine_kernel:
        return machine_kernel, "machine_kernel"
    return None, None


def _infer_kernel_from_path(raw_value: Any) -> str | None:
    """从路径文本中提取内核版本字符串"""

    if raw_value in {None, ""}:
        return None
    text = str(raw_value).replace("\\", "/")
    for pattern in _PATH_KERNEL_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group("release")
    return None


def render_machine_profile_summary(machine_profile: MachineProfile) -> str:
    """把机器快照整理成适合日志输出的摘要文本"""

    parts = [
        f"system={machine_profile.machine_system or 'unknown'}",
        f"machine_kernel={machine_profile.machine_kernel or 'unknown'}",
        f"build_target_kernel={machine_profile.build_target_kernel or 'unknown'}",
        f"source={machine_profile.build_target_kernel_source or 'unknown'}",
    ]
    if machine_profile.selected_source_dir:
        parts.append(f"source_dir={shlex.quote(machine_profile.selected_source_dir)}")
    return ", ".join(parts)
