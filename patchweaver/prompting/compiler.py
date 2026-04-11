"""Prompt 编译器。"""

from __future__ import annotations

from patchweaver.models.context import BootstrapManifest, ContextBundle
from patchweaver.models.prompt import PromptPacket


class PromptCompiler:
    """把上下文和 bootstrap 片段组合成提示包。"""

    def compile(
        self,
        *,
        stage_name: str,
        context_bundle: ContextBundle,
        bootstrap_manifest: BootstrapManifest,
        schema_name: str,
    ) -> PromptPacket:
        """生成一份最小可用的 PromptPacket。"""

        evidence_summary = "、".join(context_bundle.evidence_ids[:4]) if context_bundle.evidence_ids else "无"
        note_summary = "；".join(context_bundle.notes[:3]) if context_bundle.notes else "无"
        return PromptPacket(
            stage_name=stage_name,
            system_prompt_version="v1",
            worker_prompt_version="v1",
            schema_name=schema_name,
            budget_snapshot={"token_cost": context_bundle.token_cost},
            bootstrap_fragments=bootstrap_manifest.fragment_ids,
            prompt_sections=[
                f"阶段: {stage_name}",
                f"输出结构: {schema_name}",
                f"证据数量: {len(context_bundle.evidence_ids)}",
                f"证据摘要: {evidence_summary}",
                f"Bootstrap 数量: {len(bootstrap_manifest.fragment_ids)}",
                f"Bootstrap 开销: {bootstrap_manifest.total_token_cost}",
                f"上下文备注: {note_summary}",
            ],
        )
