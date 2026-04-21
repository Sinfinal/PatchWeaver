"""Bootstrap 片段加载"""

from __future__ import annotations

from pathlib import Path


def load_bootstrap_fragments(fragment_paths: list[Path]) -> list[str]:
    """读取 bootstrap 片段文本"""

    contents: list[str] = []
    for path in fragment_paths:
        if path.exists():
            contents.append(path.read_text(encoding="utf-8"))
    return contents

