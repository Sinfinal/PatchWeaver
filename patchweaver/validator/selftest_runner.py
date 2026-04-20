"""模块级自检执行器。"""

from __future__ import annotations

from pathlib import Path

from patchweaver.models.validation import ValidationItem


class SelftestRunner:
    """负责输出一份标准化的自检基线结果。"""

    def run(
        self,
        *,
        build_succeeded: bool,
        module_path: Path | None,
        risk_level: str,
    ) -> tuple[ValidationItem, str]:
        """根据模块产物和风险等级整理自检结果。"""

        if not build_succeeded:
            item = ValidationItem(status="pending", ok=False, detail="构建未完成，自检基线暂不执行。")
            return item, self._build_log(item, risk_level=risk_level)

        if module_path is None or not module_path.exists():
            item = ValidationItem(status="failed", ok=False, detail="未找到模块产物，自检基线无法继续。")
            return item, self._build_log(item, risk_level=risk_level)

        detail = "已完成模块产物与基本加载前置检查。"
        if risk_level == "high":
            detail += " 当前样例风险较高，后续仍应结合语义守卫和回归结果判断。"

        item = ValidationItem(status="passed", ok=True, detail=detail)
        return item, self._build_log(item, risk_level=risk_level, module_path=module_path)

    def _build_log(self, item: ValidationItem, *, risk_level: str, module_path: Path | None = None) -> str:
        """整理自检基线日志文本。"""

        return "\n".join(
            [
                f"risk_level: {risk_level}",
                f"module_path: {module_path if module_path is not None else '<missing>'}",
                f"status: {item.status}",
                f"detail: {item.detail}",
            ]
        ) + "\n"
