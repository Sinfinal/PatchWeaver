"""回归测试器。"""

from __future__ import annotations


class RegressionTester:
    """负责执行回归验证。"""

    def run(self) -> dict[str, object]:
        """返回一份占位回归结果。"""

        return {"ok": False, "detail": "当前版本未进入真实回归测试。"}

