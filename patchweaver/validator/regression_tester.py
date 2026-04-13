"""回归测试器。"""

from __future__ import annotations

from patchweaver.models.validation import ValidationItem


class RegressionTester:
    """负责执行回归验证。"""

    def run(self) -> tuple[ValidationItem, str]:
        """返回最小回归测试结果。"""

        return ValidationItem(status="skipped", ok=False, detail="当前阶段未开启回归验证。"), ""
