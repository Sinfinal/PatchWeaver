"""工具桥接层"""

from __future__ import annotations


class ToolBridge:
    """负责收敛主链工具调用入口"""

    def call(self, tool_name: str, action: str) -> dict[str, str]:
        """返回一次占位工具调用结果"""

        return {"tool_name": tool_name, "action": action, "status": "ok"}

