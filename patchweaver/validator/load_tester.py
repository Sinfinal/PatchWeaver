"""模块加载测试器"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from patchweaver.models.validation import ValidationItem


class LoadTester:
    """负责执行模块加载和卸载测试"""

    def __init__(self, build_config: Any | None = None) -> None:
        """保存构建配置，便于复用运行时约束"""

        self.build_config = build_config

    def load(self, *, module_path: Path | None) -> tuple[ValidationItem, str]:
        """执行最小模块加载测试"""

        if self.build_config is None:
            return ValidationItem(status="pending", ok=False, detail="缺少构建配置，无法执行加载测试。"), ""

        if module_path is None or not module_path.exists():
            return ValidationItem(status="pending", ok=False, detail="当前没有本地模块产物，暂不执行加载测试。"), ""

        return self._run_local_module_command(
            command=["insmod", str(module_path)],
            detail_on_success="模块加载测试通过。",
        )

    def unload(self, *, module_path: Path | None) -> tuple[ValidationItem, str]:
        """执行最小模块卸载测试"""

        if self.build_config is None:
            return ValidationItem(status="pending", ok=False, detail="缺少构建配置，无法执行卸载测试。"), ""

        module_name = self._module_name(module_path=module_path)
        if not module_name:
            return ValidationItem(status="pending", ok=False, detail="无法确定模块名，暂不执行卸载测试。"), ""

        disable_item, disable_log = self._disable_livepatch_if_needed(module_name=module_name)
        if disable_item.status == "failed":
            return disable_item, disable_log

        wait_log = self._wait_livepatch_transition(module_name=module_name)
        return self._run_local_module_command(
            command=["rmmod", module_name],
            detail_on_success="模块卸载测试通过。",
            prefix_log=disable_log + wait_log,
        )

    def _run_local_module_command(
        self,
        *,
        command: list[str],
        detail_on_success: str,
        prefix_log: str = "",
    ) -> tuple[ValidationItem, str]:
        """在本地执行模块相关命令"""

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
        if prefix_log:
            log_text = prefix_log.rstrip() + "\n\n" + log_text
        if result.returncode == 0:
            return ValidationItem(status="passed", ok=True, detail=detail_on_success, command=" ".join(command)), log_text
        return ValidationItem(status="failed", ok=False, detail="模块操作命令执行失败。", command=" ".join(command)), log_text

    def _module_name(self, *, module_path: Path | None) -> str | None:
        """从模块路径中推导模块名"""

        if module_path is not None:
            modinfo = self._modinfo_name(module_path)
            if modinfo:
                return modinfo
            return module_path.stem.replace("-", "_")
        return None

    def _modinfo_name(self, module_path: Path) -> str | None:
        """优先读取模块自身声明的内核模块名"""

        try:
            result = subprocess.run(
                ["modinfo", "-F", "name", str(module_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None
        name = result.stdout.strip()
        return name or None

    def _disable_livepatch_if_needed(self, *, module_name: str) -> tuple[ValidationItem, str]:
        """livepatch 模块卸载前需要先关闭 enabled"""

        enabled_path = Path("/sys/kernel/livepatch") / module_name / "enabled"
        if not enabled_path.exists():
            return ValidationItem(status="skipped", ok=True, detail="未发现 livepatch sysfs 状态，无需禁用。"), ""

        try:
            enabled_path.write_text("0\n", encoding="utf-8")
        except OSError as exc:
            log_text = f"command: echo 0 > {enabled_path}\n\n[stderr]\n{exc}\n"
            return ValidationItem(status="failed", ok=False, detail="livepatch 禁用失败。", command=f"echo 0 > {enabled_path}"), log_text

        log_text = f"command: echo 0 > {enabled_path}\n\n[stdout]\nlivepatch disabled\n"
        return ValidationItem(status="passed", ok=True, detail="livepatch 已禁用。", command=f"echo 0 > {enabled_path}"), log_text

    def _wait_livepatch_transition(self, *, module_name: str) -> str:
        """等待 livepatch 状态迁移完成后再卸载"""

        patch_dir = Path("/sys/kernel/livepatch") / module_name
        transition_path = patch_dir / "transition"
        lines = [f"command: wait livepatch transition {module_name}", "", "[stdout]"]
        for index in range(20):
            if not patch_dir.exists():
                lines.append(f"try={index + 1} state=removed")
                break
            transition = transition_path.read_text(encoding="utf-8", errors="replace").strip() if transition_path.exists() else "none"
            lines.append(f"try={index + 1} transition={transition}")
            if transition in {"0", "none", ""}:
                break
            time.sleep(0.5)
        return "\n".join(lines) + "\n"

    def _compose_log(self, *, command: str, stdout_text: str, stderr_text: str, exit_code: int) -> str:
        """整理统一的模块测试日志"""

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
