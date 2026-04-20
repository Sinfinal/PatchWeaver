"""模块加载测试器。"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from patchweaver.models.validation import ValidationItem


class LoadTester:
    """负责执行模块加载和卸载测试。"""

    def __init__(self, build_config: Any | None = None) -> None:
        """保存构建配置，便于复用运行时约束。"""

        self.build_config = build_config

    def load(self, *, module_path: Path | None) -> tuple[ValidationItem, str]:
        """执行最小模块加载测试。"""

        if self.build_config is None:
            return ValidationItem(status="pending", ok=False, detail="缺少构建配置，无法执行加载测试。"), ""

        if module_path is None or not module_path.exists():
            return ValidationItem(status="pending", ok=False, detail="当前没有本地模块产物，暂不执行加载测试。"), ""

        return self._run_local_module_command(
            command=["insmod", str(module_path)],
            detail_on_success="模块加载测试通过。",
        )

    def unload(self, *, module_path: Path | None) -> tuple[ValidationItem, str]:
        """执行最小模块卸载测试。"""

        if self.build_config is None:
            return ValidationItem(status="pending", ok=False, detail="缺少构建配置，无法执行卸载测试。"), ""

        module_name = self._module_name(module_path=module_path)
        if not module_name:
            return ValidationItem(status="pending", ok=False, detail="无法确定模块名，暂不执行卸载测试。"), ""

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

    def _module_name(self, *, module_path: Path | None) -> str | None:
        """从模块路径中推导模块名。"""

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
