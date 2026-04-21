"""提示模板加载器"""

from __future__ import annotations

from pathlib import Path


class TemplateLoader:
    """负责读取提示模板文件"""

    def load(self, path: Path) -> str:
        """返回模板文本"""

        return path.read_text(encoding="utf-8")

    def load_optional(self, path: Path, *, fallback: str) -> str:
        """在模板不存在时返回回退文本"""

        if not path.exists():
            return fallback
        return self.load(path)
