"""Prompt 编译器"""

from __future__ import annotations

from pathlib import Path

from patchweaver.models.context import BootstrapManifest, ContextBundle
from patchweaver.models.prompt import PromptPacket
from patchweaver.models.skill import SkillRouteDecision
from patchweaver.prompting.prompt_library import PromptLibrary


class PromptCompiler:
    """把上下文和 bootstrap 片段组合成提示包"""

    def __init__(self, project_root: Path) -> None:
        """初始化模板库"""

        self.library = PromptLibrary(project_root)

    def compile(
        self,
        *,
        stage_name: str,
        context_bundle: ContextBundle,
        bootstrap_manifest: BootstrapManifest,
        schema_name: str,
        route: SkillRouteDecision | None = None,
    ) -> PromptPacket:
        """生成一份最小可用的 PromptPacket"""

        evidence_summary = "、".join(context_bundle.evidence_ids[:4]) if context_bundle.evidence_ids else "无"
        note_summary = "；".join(context_bundle.notes[:3]) if context_bundle.notes else "无"
        memory_summary = "；".join(context_bundle.memory_summaries[:3]) if context_bundle.memory_summaries else "无"
        selected_skill = route.selected_skill if route is not None else None
        contract_summary = "；".join(route.contract_summary[:3]) if route is not None and route.contract_summary else "无"
        return PromptPacket(
            stage_name=stage_name,
            system_prompt_version="v1",
            worker_prompt_version="v1",
            schema_name=schema_name,
            budget_snapshot={
                "token_cost": context_bundle.token_cost,
                "duplicate_hits": context_bundle.duplicate_hits,
                "memory_hits": context_bundle.memory_hits,
            },
            bootstrap_fragments=bootstrap_manifest.fragment_ids,
            prompt_sections=[
                self.library.stage_instruction(stage_name),
                self.library.schema_contract(schema_name),
                f"阶段: {stage_name}",
                f"选中 Skill: {selected_skill or 'direct_worker'}",
                f"Skill 契约摘要: {contract_summary}",
                f"输出结构: {schema_name}",
                f"证据数量: {len(context_bundle.evidence_ids)}",
                f"证据摘要: {evidence_summary}",
                f"记忆摘要: {memory_summary}",
                f"Bootstrap 数量: {len(bootstrap_manifest.fragment_ids)}",
                f"Bootstrap 开销: {bootstrap_manifest.total_token_cost}",
                f"上下文备注: {note_summary}",
            ],
        )
