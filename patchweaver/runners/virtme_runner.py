"""virtme 运行器骨架。"""

from __future__ import annotations


class VirtmeRunner:
    """负责封装后续的虚拟机验证入口。"""

    def launch(self) -> dict[str, str]:
        """返回一份占位启动结果。"""

        return {"status": "pending", "detail": "virtme-ng 尚未接入。"}

