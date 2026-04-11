"""语义预检查器。"""

from __future__ import annotations


class SemanticPrecheck:
    """负责执行轻量静态语义预检查。"""

    def run(self) -> dict[str, object]:
        """返回一份占位预检查结果。"""

        return {"ok": True, "detail": "当前版本仅保留占位预检查。"}

