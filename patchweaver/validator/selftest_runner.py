"""模块级自检执行器。"""

from __future__ import annotations


class SelftestRunner:
    """负责组织 livepatch selftests。"""

    def run(self) -> dict[str, object]:
        """返回一份占位自检结果。"""

        return {"ok": False, "detail": "当前版本未接入真实 selftests。"}

