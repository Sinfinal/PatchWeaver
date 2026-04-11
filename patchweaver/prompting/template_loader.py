"""提示模板加载器。"""

from __future__ import annotations

from pathlib import Path


class TemplateLoader:
    """负责读取提示模板文件。"""

    def load(self, path: Path) -> str:
        """返回模板文本。"""

        return path.read_text(encoding="utf-8")

