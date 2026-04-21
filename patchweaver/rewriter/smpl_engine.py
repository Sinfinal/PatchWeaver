"""SmPL 层执行器"""

from __future__ import annotations

from pathlib import Path

from patchweaver.models.rewrite import RewritePlan, TransformationStep


class SmPLEngine:
    """负责挂接 Coccinelle/SmPL 规则入口"""

    def __init__(self, project_root: Path) -> None:
        """初始化 SmPL 规则目录"""

        self.smpl_dir = project_root / "recipes" / "smpl"

    def apply(self, *, plan: RewritePlan, patch_text: str) -> tuple[str, TransformationStep]:
        """返回当前阶段的 SmPL 层结果"""

        recipe_name = plan.selected_recipe or "direct_apply_patch"
        smpl_path = self.smpl_dir / f"{recipe_name}.cocci"
        if smpl_path.exists() and recipe_name != "direct_apply_patch":
            summary = f"已定位 SmPL 规则 {smpl_path.name}，当前版本保留 diff 形态并记录命中轨迹。"
        elif smpl_path.exists():
            summary = f"已定位 SmPL 规则 {smpl_path.name}，当前候选无需额外结构化改写。"
        else:
            summary = "当前候选未要求额外 SmPL 变换。"

        return patch_text, TransformationStep(
            step_id="smpl-001",
            engine="smpl",
            action="pass-through",
            recipe_name=plan.selected_recipe,
            target_files=plan.target_files,
            summary=summary,
        )
