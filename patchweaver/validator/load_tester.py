"""模块加载测试器。"""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

import paramiko

from patchweaver.models.validation import ValidationItem


class LoadTester:
    """负责执行模块加载和卸载测试。"""

    def __init__(self, build_config: Any | None = None) -> None:
        """保存构建配置，便于复用 SSH 后端。"""

        self.build_config = build_config

    def load(self, *, module_path: Path | None, remote_module_path: str | None = None) -> tuple[ValidationItem, str]:
        """执行最小模块加载测试。"""

        if self.build_config is None:
            return ValidationItem(status="pending", ok=False, detail="缺少构建配置，无法执行加载测试。"), ""

        if self.build_config.build_backend == "ssh":
            if not remote_module_path:
                return ValidationItem(status="pending", ok=False, detail="当前没有远端模块路径，暂不执行远端加载测试。"), ""
            return self._run_remote_module_command(
                command=f"insmod {shlex.quote(remote_module_path)}",
                detail_on_success="模块加载测试通过。",
            )

        if module_path is None or not module_path.exists():
            return ValidationItem(status="pending", ok=False, detail="当前没有本地模块产物，暂不执行加载测试。"), ""

        return self._run_local_module_command(
            command=["insmod", str(module_path)],
            detail_on_success="模块加载测试通过。",
        )

    def unload(self, *, module_path: Path | None, remote_module_path: str | None = None) -> tuple[ValidationItem, str]:
        """执行最小模块卸载测试。"""

        if self.build_config is None:
            return ValidationItem(status="pending", ok=False, detail="缺少构建配置，无法执行卸载测试。"), ""

        module_name = self._module_name(module_path=module_path, remote_module_path=remote_module_path)
        if not module_name:
            return ValidationItem(status="pending", ok=False, detail="无法确定模块名，暂不执行卸载测试。"), ""

        if self.build_config.build_backend == "ssh":
            return self._run_remote_module_command(
                command=f"rmmod {shlex.quote(module_name)}",
                detail_on_success="模块卸载测试通过。",
            )

        return self._run_local_module_command(
            command=["rmmod", module_name],
            detail_on_success="模块卸载测试通过。",
        )

    def _run_local_module_command(self, *, command: list[str], detail_on_success: str) -> tuple[ValidationItem, str]:
        """在本地执行模块相关命令。"""

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        except FileNotFoundError:
            return ValidationItem(status="failed", ok=False, detail=f"未找到命令：{command[0]}", command=" ".join(command)), ""

        log_text = self._compose_log(command=" ".join(command), stdout_text=result.stdout, stderr_text=result.stderr, exit_code=result.returncode)
        if result.returncode == 0:
            return ValidationItem(status="passed", ok=True, detail=detail_on_success, command=" ".join(command)), log_text
        return ValidationItem(status="failed", ok=False, detail="模块操作命令执行失败。", command=" ".join(command)), log_text

    def _run_remote_module_command(self, *, command: str, detail_on_success: str) -> tuple[ValidationItem, str]:
        """在远端执行模块相关命令。"""

        password = self._remote_password()
        if not password:
            return ValidationItem(status="failed", ok=False, detail="缺少远端密码环境变量，无法执行远端模块测试。", command=command), ""

        client: paramiko.SSHClient | None = None
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                hostname=self.build_config.remote_host,
                port=self.build_config.remote_port,
                username=self.build_config.remote_username,
                password=password,
                timeout=self.build_config.remote_connect_timeout_sec,
            )
            stdin, stdout, stderr = client.exec_command(command, timeout=60)
            stdout_text = stdout.read().decode("utf-8", errors="replace")
            stderr_text = stderr.read().decode("utf-8", errors="replace")
            exit_code = stdout.channel.recv_exit_status()
            log_text = self._compose_log(command=command, stdout_text=stdout_text, stderr_text=stderr_text, exit_code=exit_code)
            if exit_code == 0:
                return ValidationItem(status="passed", ok=True, detail=detail_on_success, command=command), log_text
            return ValidationItem(status="failed", ok=False, detail="远端模块操作命令执行失败。", command=command), log_text
        except Exception as exc:
            return ValidationItem(status="failed", ok=False, detail=f"远端模块测试执行失败：{exc}", command=command), ""
        finally:
            if client is not None:
                client.close()

    def _remote_password(self) -> str | None:
        """读取远端密码。"""

        if self.build_config is None or not self.build_config.remote_password_env:
            return None
        return os.getenv(self.build_config.remote_password_env)

    def _module_name(self, *, module_path: Path | None, remote_module_path: str | None) -> str | None:
        """从模块路径中推导模块名。"""

        if remote_module_path:
            return Path(remote_module_path).stem
        if module_path is not None:
            return module_path.stem
        return None

    def _compose_log(self, *, command: str, stdout_text: str, stderr_text: str, exit_code: int) -> str:
        """整理统一的模块测试日志。"""

        return "\n".join(
            [
                f"command: {command}",
                "",
                "[stdout]",
                stdout_text.strip() or "<empty>",
                "",
                "[stderr]",
                stderr_text.strip() or "<empty>",
                "",
                f"exit_code: {exit_code}",
            ]
        ) + "\n"
