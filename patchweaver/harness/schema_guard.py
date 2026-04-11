"""结构化输出守卫。"""

from __future__ import annotations


class SchemaGuard:
    """负责做最小的结构完整性检查。"""

    def require_value(self, value, *, label: str) -> None:
        """要求目标值不能为空。"""

        if value in (None, "", [], {}):
            raise ValueError(f"{label} 不能为空。")

