"""截断标记工具"""

from __future__ import annotations


def build_truncation_mark(source_name: str, original_size: int, kept_size: int) -> str:
    """生成一条简单的截断标记"""

    return f"{source_name}: {original_size} -> {kept_size}"

