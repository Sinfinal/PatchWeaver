"""模板层执行器"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from patchweaver.models.rewrite import TransformationStep


class TemplateEngine:
    """负责按 recipe 模板渲染 patch 文本"""

    def __init__(self, project_root: Path) -> None:
        """初始化模板目录"""

        self.templates_dir = project_root / "recipes" / "templates"
        self.environment = Environment(loader=FileSystemLoader(str(self.templates_dir)), autoescape=False)

    def render(
        self,
        *,
        recipe_name: str | None,
        patch_text: str,
        target_files: list[str],
    ) -> tuple[str, TransformationStep]:
        """按选中的 recipe 生成模板层结果"""

        template_name = f"{recipe_name}.patch.j2" if recipe_name else ""
        template_path = self.templates_dir / template_name
        if recipe_name and template_path.exists():
            template = self.environment.get_template(template_name)
            rendered = template.render(patch_text=patch_text, target_files=target_files)
            summary = f"命中模板 {template_name}，已生成真实 unified diff。"
        else:
            rendered = patch_text
            summary = "未命中专用模板，沿用来源 patch 作为模板层输出。"

        return rendered, TransformationStep(
            step_id="template-001",
            engine="template",
            action="render",
            recipe_name=recipe_name,
            target_files=target_files,
            summary=summary,
        )
