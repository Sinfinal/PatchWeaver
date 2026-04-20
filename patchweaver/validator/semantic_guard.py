"""语义守卫。"""

from __future__ import annotations

from pathlib import Path

from patchweaver.models.validation import ValidationItem


class SemanticGuard:
    """根据静态预检和动态执行结果给出语义守卫结论。"""

    def run(
        self,
        *,
        semantic_precheck: ValidationItem,
        rewritten_patch_path: Path,
        build_succeeded: bool,
        module_path: Path | None,
        load_result: ValidationItem,
        smoke_result: ValidationItem,
        regression_result: ValidationItem,
    ) -> ValidationItem:
        """输出更贴近第三期需求的语义守卫结果。"""

        if semantic_precheck.status == "failed":
            return ValidationItem(status="failed", ok=False, detail=f"语义预检查未通过：{semantic_precheck.detail}")

        if not build_succeeded:
            return ValidationItem(status="pending", ok=False, detail="构建尚未成功，语义守卫暂保持待执行状态。")

        if module_path is None or not module_path.exists():
            return ValidationItem(status="failed", ok=False, detail="构建报告为成功，但本地未找到模块产物，语义守卫无法确认。")

        content = rewritten_patch_path.read_text(encoding="utf-8", errors="replace")
        changed_lines = [
            line
            for line in content.splitlines()
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
        ]
        if not changed_lines:
            return ValidationItem(status="failed", ok=False, detail="改写补丁没有检测到有效变更行，语义守卫拒绝通过。")

        if load_result.status == "failed":
            return ValidationItem(status="failed", ok=False, detail="模块未能完成加载，当前更像模块问题而非语义通过。")

        if smoke_result.status == "failed":
            return ValidationItem(status="failed", ok=False, detail="模块已加载，但冒烟验证失败，存在功能偏移风险。")

        if regression_result.status == "failed":
            return ValidationItem(status="failed", ok=False, detail="当前轮重复落入历史失败路径，语义守卫不建议放行。")

        return ValidationItem(status="passed", ok=True, detail="静态预检、模块产物和动态基线均未发现明显语义偏移。")
