"""原语模板库。"""

from __future__ import annotations


class PrimitiveTemplates:
    """负责提供 MVP 阶段的模板文本。"""

    def render(self, primitive_name: str) -> str:
        """返回指定原语的模板说明。"""

        return f"{primitive_name} 模板待接入真实实现。"

