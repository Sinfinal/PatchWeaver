"""语义预检查器。"""

from __future__ import annotations

from pathlib import Path

from patchweaver.models.validation import ValidationItem


class SemanticPrecheck:
    """负责执行轻量静态语义预检查。"""

    def run(self, *, rewritten_patch_path: Path) -> ValidationItem:
        """检查改写补丁是否至少满足最基本的可读与非占位要求。"""

        if not rewritten_patch_path.exists():
            return ValidationItem(status="failed", ok=False, detail="改写补丁文件不存在，无法执行语义预检查。")

        content = rewritten_patch_path.read_text(encoding="utf-8", errors="replace")
        stripped = content.strip()
        if not stripped:
            return ValidationItem(status="failed", ok=False, detail="改写补丁文件为空，无法进入后续验证。")

        lowered = stripped.lower()
        if "# rewrite plan:" in lowered or "mvp 阶段仅写入占位" in lowered or "placeholder" in lowered:
            return ValidationItem(status="failed", ok=False, detail="改写补丁仍是占位内容，未进入真实 unified diff 形态。")

        if "diff --git " not in content:
            return ValidationItem(status="failed", ok=False, detail="改写补丁缺少 `diff --git` 头，当前不像合法 unified diff。")

        if "@@" not in content:
            return ValidationItem(status="failed", ok=False, detail="改写补丁缺少 hunk 标记 `@@`，当前不能视为有效改写结果。")

        return ValidationItem(status="passed", ok=True, detail="语义预检查通过，补丁具备基础 unified diff 结构。")
