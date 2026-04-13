"""语义守卫。"""

from __future__ import annotations

from pathlib import Path

from patchweaver.models.validation import ValidationItem


class SemanticGuard:
    """根据静态预检和动态执行结果给出最小语义守卫结论。"""

    def run(
        self,
        *,
        semantic_precheck: ValidationItem,
        rewritten_patch_path: Path,
        build_succeeded: bool,
        module_path: Path | None,
    ) -> ValidationItem:
        """输出最小语义守卫结果。"""

        if semantic_precheck.status == "failed":
            return ValidationItem(status="failed", ok=False, detail=f"语义预检查未通过：{semantic_precheck.detail}")

        if not build_succeeded:
            return ValidationItem(status="pending", ok=False, detail="构建尚未成功，语义守卫暂保持待执行状态。")

        if module_path is None or not module_path.exists():
            return ValidationItem(status="failed", ok=False, detail="构建报告为成功，但本地未找到模块产物，语义守卫无法确认。")

        content = rewritten_patch_path.read_text(encoding="utf-8", errors="replace")
        changed_lines = [line for line in content.splitlines() if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))]
        if not changed_lines:
            return ValidationItem(status="failed", ok=False, detail="改写补丁没有检测到有效变更行，语义守卫拒绝通过。")

        return ValidationItem(status="passed", ok=True, detail="构建成功且补丁具备实际变更行，最小语义守卫通过。")
