"""冒烟测试器。"""

from __future__ import annotations


class SmokeTester:
    """负责执行最小冒烟验证。"""

    def run(self) -> dict[str, object]:
        """返回一份占位冒烟结果。"""

        return {"ok": False, "detail": "当前版本未进入真实冒烟测试。"}

