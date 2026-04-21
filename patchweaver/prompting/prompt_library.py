"""阶段提示模板库"""

from __future__ import annotations

import re
from pathlib import Path

from patchweaver.prompting.template_loader import TemplateLoader


class PromptLibrary:
    """负责加载阶段模板和结构契约说明"""

    DEFAULT_STAGE_TEMPLATES = {
        "retrieval": "你负责检索真实 CVE 来源链，优先 stable backport，其次 upstream，输出必须可追溯。",
        "semantic_card": "你负责抽取最小修复语义边界，聚焦根因、关键调用和必须保持的副作用。",
        "constraint_diagnosis": "你负责识别 livepatch 约束、风险类型和所需原语，避免给出与热补丁约束冲突的建议。",
        "rewrite_recipe": "你负责选择最合适的 recipe 和原语组合，目标是输出可 apply、可解释、可构建的改写方案。",
        "failure_analysis": "你负责阅读构建失败证据，区分环境问题、补丁内容问题和 kpatch 约束问题，并给出下一轮最有价值的改进方向。",
        "validation": "你负责整理验证输入，区分语义预检查、加载卸载和冒烟验证的层次，避免把待执行状态误判为成功。",
        "reporting": "你负责把阶段证据、失败归因和最终状态整理成评委可读的结果摘要，保持证据链完整。",
    }

    def __init__(self, project_root: Path, loader: TemplateLoader | None = None) -> None:
        """绑定项目根目录"""

        self.project_root = project_root
        self.loader = loader or TemplateLoader()

    def stage_instruction(self, stage_name: str) -> str:
        """读取阶段模板说明"""

        stage_path = self.project_root / "prompts" / "stages" / f"{stage_name}.md"
        fallback = self.DEFAULT_STAGE_TEMPLATES.get(stage_name, f"{stage_name} 阶段提示模板待补充。")
        return self.loader.load_optional(stage_path, fallback=fallback)

    def schema_contract(self, schema_name: str) -> str:
        """读取结构契约说明"""

        schema_key = re.sub(r"(?<!^)(?=[A-Z])", "_", schema_name).lower()
        fallback = f"输出需满足 {schema_name} 对应的结构约束，并保持字段命名稳定。"
        candidate_paths = [
            self.project_root / "prompts" / "contracts" / f"{schema_key}.md",
            self.project_root / "prompts" / "contracts" / f"{schema_key}_schema.md",
        ]
        for contract_path in candidate_paths:
            if contract_path.exists():
                return self.loader.load(contract_path)
        return fallback
