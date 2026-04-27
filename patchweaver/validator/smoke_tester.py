"""冒烟测试器"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from patchweaver.models.validation import ValidationItem


class SmokeTester:
    """负责执行最小冒烟验证"""

    def __init__(self, verify_config: Any | None = None, project_root: Path | None = None) -> None:
        """保存验证配置和项目根目录"""

        self.verify_config = verify_config
        self.project_root = project_root

    def run(self) -> tuple[ValidationItem, str]:
        """执行最小冒烟测试"""

        if self.verify_config is None or self.project_root is None:
            return ValidationItem(status="pending", ok=False, detail="缺少验证配置或项目根目录，暂不执行冒烟测试。"), ""

        script_path = Path(self.verify_config.smoke_test_script)
        if not script_path.is_absolute():
            script_path = (self.project_root / script_path).resolve()

        if not script_path.exists():
            return ValidationItem(status="pending", ok=False, detail=f"未找到冒烟测试脚本：{script_path}"), ""

        command = ["bash", str(script_path)] if script_path.suffix == ".sh" else [str(script_path)]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                cwd=self.project_root,
                shell=False,
            )
        except OSError as exc:
            return ValidationItem(status="failed", ok=False, detail=f"冒烟测试启动失败：{exc}", command=" ".join(command)), ""

        log_text = "\n".join(
            [
                f"command: {' '.join(command)}",
                "",
                "[stdout]",
                result.stdout.strip() or "<empty>",
                "",
                "[stderr]",
                result.stderr.strip() or "<empty>",
                "",
                f"exit_code: {result.returncode}",
            ]
        ) + "\n"
        if result.returncode == 0:
            return ValidationItem(status="passed", ok=True, detail="冒烟测试通过。", command=" ".join(command)), log_text
        return ValidationItem(status="failed", ok=False, detail="冒烟测试未通过。", command=" ".join(command)), log_text
