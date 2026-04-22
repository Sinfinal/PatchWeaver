"""基于模型的语义卡片补全"""

from __future__ import annotations

import json
import re
from pathlib import Path
from time import perf_counter
from typing import Any

from patchweaver.config.models import ModelsConfig
from patchweaver.models.context import ContextBundle
from patchweaver.models.model_interaction import ModelInteractionRecord
from patchweaver.models.patch import PatchBundle
from patchweaver.models.prompt import PromptPacket
from patchweaver.models.semantic import SemanticCard, SemanticCardEnrichmentTrace
from patchweaver.models.skill import SkillRouteDecision
from patchweaver.models.task import TaskContext
from patchweaver.observability.model_interaction_logger import ModelInteractionLogger
from patchweaver.prompting.model_client import ChatJsonResult, ModelClientError, OpenAICompatibleChatClient
from patchweaver.utils.path_policy import to_project_relative


class SemanticCardEnricher:
    """负责在确定性卡片基础上做一层模型补全"""

    def __init__(
        self,
        models_config: ModelsConfig | None,
        *,
        project_root: Path | None = None,
        chat_client: OpenAICompatibleChatClient | None = None,
    ) -> None:
        """保存模型配置，并按需装配默认聊天客户端"""

        self.models_config = models_config
        self.project_root = project_root.resolve() if project_root is not None else None
        self.chat_client = chat_client or self._build_default_client(models_config)
        self.interaction_logger = self._build_interaction_logger(models_config)

    def enrich(
        self,
        *,
        task: TaskContext,
        patch_bundle: PatchBundle,
        draft_card: SemanticCard,
        prompt_packet: PromptPacket,
        context_bundle: ContextBundle,
        route: SkillRouteDecision | None,
        patch_text: str,
        prompt_packet_path: Path | None = None,
        source_evidence_path: Path | None = None,
    ) -> tuple[SemanticCard, SemanticCardEnrichmentTrace]:
        """使用模型对确定性草稿做增量补全"""

        selected_skill = route.selected_skill if route is not None else None
        base_trace = SemanticCardEnrichmentTrace(
            status="skipped",
            applied=False,
            provider=getattr(self.models_config, "provider", None),
            model_name=self._model_name(),
            selected_skill=selected_skill,
            prompt_packet_path=str(prompt_packet_path) if prompt_packet_path is not None else None,
            source_evidence_path=str(source_evidence_path) if source_evidence_path is not None else None,
            evidence_ids=list(context_bundle.evidence_ids),
            draft_card=draft_card.model_dump(mode="json"),
            record_mode=self._interaction_record_mode(),
            context_token_cost=context_bundle.token_cost,
            context_evidence_count=len(context_bundle.evidence_ids),
            context_duplicate_hits=context_bundle.duplicate_hits,
            context_memory_hits=context_bundle.memory_hits,
        )

        if self.models_config is None:
            return draft_card, base_trace.model_copy(update={"reason": "未提供模型配置，跳过语义补全。"})
        if self.chat_client is None:
            reason = (
                f"缺少可用的 {self.models_config.api_key_env}，跳过语义补全。"
                if self.models_config.resolve_api_key() is None
                else "当前模型接口模式未接入语义补全客户端。"
            )
            return draft_card, base_trace.model_copy(update={"reason": reason})

        system_prompt = self._build_system_prompt(prompt_packet)
        user_prompt = self._build_user_prompt(
            task=task,
            patch_bundle=patch_bundle,
            draft_card=draft_card,
            prompt_packet=prompt_packet,
            context_bundle=context_bundle,
            route=route,
            patch_text=patch_text,
        )
        interaction_artifact_path = task.workspace_dir / "analysis" / "trace" / "semantic_card_model_interaction.json"
        started_at = perf_counter()

        try:
            response = self.chat_client.chat_json(
                model=self._model_name(),
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.1,
            )
        except (ModelClientError, ValueError, KeyError) as exc:
            duration_ms = max(0, int((perf_counter() - started_at) * 1000))
            interaction_record_path = self._record_interaction(
                task=task,
                stage_name=prompt_packet.stage_name,
                route=route,
                prompt_packet=prompt_packet,
                context_bundle=context_bundle,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                artifact_path=interaction_artifact_path,
                failure_reason=f"模型补全失败: {exc}",
                duration_ms=duration_ms,
                prompt_packet_path=prompt_packet_path,
                source_evidence_path=source_evidence_path,
            )
            return draft_card, base_trace.model_copy(
                update={
                    "status": "failed",
                    "reason": f"模型补全失败: {exc}",
                    "duration_ms": duration_ms,
                    "interaction_record_path": self._relativize_path(interaction_record_path),
                }
            )

        normalized_output = self._normalize_output(response.payload)
        duration_ms = max(0, int((perf_counter() - started_at) * 1000))
        interaction_record_path = self._record_interaction(
            task=task,
            stage_name=prompt_packet.stage_name,
            route=route,
            prompt_packet=prompt_packet,
            context_bundle=context_bundle,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response=response,
            artifact_path=interaction_artifact_path,
            duration_ms=duration_ms,
            prompt_packet_path=prompt_packet_path,
            source_evidence_path=source_evidence_path,
            parsed_payload=normalized_output,
        )
        merged_card, merged_fields = self._merge_card(draft_card, normalized_output)
        if not merged_fields:
            return draft_card, base_trace.model_copy(
                update={
                    "status": "skipped",
                    "reason": "模型返回了结构化结果，但没有产生有效增量。",
                    "usage": response.usage,
                    "model_output": normalized_output,
                    "raw_response_text": self._clip_text(response.raw_content, limit=1200),
                    "duration_ms": duration_ms,
                    "interaction_record_path": self._relativize_path(interaction_record_path),
                }
            )

        return merged_card, base_trace.model_copy(
            update={
                "status": "applied",
                "applied": True,
                "model_name": response.model_name or self._model_name(),
                "merged_fields": merged_fields,
                "usage": response.usage,
                "model_output": normalized_output,
                "raw_response_text": self._clip_text(response.raw_content, limit=1200),
                "duration_ms": duration_ms,
                "interaction_record_path": self._relativize_path(interaction_record_path),
            }
        )

    def _build_interaction_logger(self, models_config: ModelsConfig | None) -> ModelInteractionLogger | None:
        """按配置决定是否启用模型交互记录写入器"""

        if models_config is None or self.project_root is None:
            return None
        if models_config.interaction_record_mode == "off":
            return None
        return ModelInteractionLogger(
            self.project_root,
            jsonl_path=models_config.interaction_jsonl_path,
            record_mode=models_config.interaction_record_mode,
        )

    def _build_default_client(self, models_config: ModelsConfig | None) -> OpenAICompatibleChatClient | None:
        """按配置创建默认模型客户端"""

        if models_config is None:
            return None
        if models_config.endpoint_mode != "openai_compatible":
            return None
        api_key = models_config.resolve_api_key()
        if not api_key:
            return None
        return OpenAICompatibleChatClient(
            base_url=models_config.base_url,
            api_key=api_key,
        )

    def _model_name(self) -> str:
        """返回当前语义补全使用的模型名"""

        if self.models_config is None:
            return "unknown"
        return self.models_config.development_model or self.models_config.default_model

    def _interaction_record_mode(self) -> str | None:
        """返回当前模型交互记录模式"""

        if self.models_config is None:
            return None
        return self.models_config.interaction_record_mode

    def _relativize_path(self, path: Path | None) -> str | None:
        """把项目内路径统一转换成相对源码根目录的展示格式"""

        if path is None:
            return None
        return to_project_relative(self.project_root, path)

    def _build_system_prompt(self, prompt_packet: PromptPacket) -> str:
        """组合模型侧系统提示"""

        parts = [
            "你是 PatchWeaver 的 semantic_card 阶段补全器。",
            "你的任务是在确定性语义卡片草稿基础上，只做证据充分的补充和收敛。",
            "禁止编造补丁中未出现的函数、文件、调用链和语义条件。",
            "输出必须是一个 JSON 对象，只允许包含 root_cause、must_keep_conditions、must_keep_side_effects、critical_calls、touched_files、touched_functions 这 6 个字段。",
            "如果某个字段没有新的确定信息，可以返回空字符串或空数组。",
        ]
        parts.extend(prompt_packet.prompt_sections[:3])
        return "\n".join(parts)

    def _build_user_prompt(
        self,
        *,
        task: TaskContext,
        patch_bundle: PatchBundle,
        draft_card: SemanticCard,
        prompt_packet: PromptPacket,
        context_bundle: ContextBundle,
        route: SkillRouteDecision | None,
        patch_text: str,
    ) -> str:
        """组合用户提示，显式带入 prompt packet、来源证据和草稿卡片"""

        source_evidence = [
            {
                "source_name": item.source_name,
                "stage": item.stage,
                "preferred": item.preferred,
                "commit_id": item.commit_id,
                "url": item.url,
                "summary": self._clip_text(item.summary or "", limit=220),
            }
            for item in patch_bundle.source_evidence[:6]
        ]
        context_spans = [
            {
                "evidence_id": span.evidence_id,
                "source_type": span.source_type,
                "source_path": span.source_path,
                "excerpt": self._clip_text(span.excerpt, limit=260),
            }
            for span in context_bundle.source_spans[:6]
        ]
        prompt_payload = {
            "task": {
                "task_id": task.task_id,
                "cve_id": task.cve_id,
                "target_kernel": task.target_kernel,
            },
            "route": {
                "selected_skill": route.selected_skill if route is not None else None,
                "selection_reason": route.selection_reason if route is not None else None,
                "contract_summary": route.contract_summary if route is not None else [],
            },
            "prompt_sections": prompt_packet.prompt_sections,
            "draft_semantic_card": draft_card.model_dump(mode="json"),
            "patch_bundle": {
                "commit_message": patch_bundle.commit_message,
                "upstream_commit": patch_bundle.upstream_commit,
                "stable_commit": patch_bundle.stable_commit,
                "affected_files": patch_bundle.affected_files,
            },
            "source_evidence": source_evidence,
            "context_notes": context_bundle.notes,
            "context_spans": context_spans,
            "normalized_patch_excerpt": self._clip_text(patch_text, limit=5000),
            "output_rules": [
                "root_cause 要明确漏洞根因和条件变化，不要写空话。",
                "must_keep_conditions 写关键判断式，优先保留补丁新增条件。",
                "must_keep_side_effects 写补丁必须保留的返回、调用、赋值或状态动作。",
                "critical_calls 只保留与修复语义直接相关的调用。",
                "touched_files 和 touched_functions 只能填写 patch 中能直接定位到的对象。",
            ],
        }
        return "请依据下面的输入补全 SemanticCard。\n" + json.dumps(
            prompt_payload,
            ensure_ascii=False,
            indent=2,
        )

    def _record_interaction(
        self,
        *,
        task: TaskContext,
        stage_name: str,
        route: SkillRouteDecision | None,
        prompt_packet: PromptPacket,
        context_bundle: ContextBundle,
        system_prompt: str,
        user_prompt: str,
        artifact_path: Path,
        duration_ms: int,
        prompt_packet_path: Path | None,
        source_evidence_path: Path | None,
        response: ChatJsonResult | None = None,
        parsed_payload: dict[str, Any] | None = None,
        failure_reason: str | None = None,
    ) -> Path | None:
        """把单次模型调用整理成结构化记录并落盘"""

        if self.interaction_logger is None or self.models_config is None:
            return None

        record_mode = self.models_config.interaction_record_mode
        response_text = response.raw_content if response is not None else ""
        normalized_payload = parsed_payload or (response.payload if response is not None else None)
        record = ModelInteractionRecord(
            stage_name=stage_name,
            task_id=task.task_id,
            attempt_no=0,
            status="failed" if failure_reason else "applied",
            success=failure_reason is None,
            provider=self.models_config.provider,
            endpoint_mode=self.models_config.endpoint_mode,
            topology=self.models_config.topology,
            model_name=(response.model_name if response is not None else None) or self._model_name(),
            selected_skill=route.selected_skill if route is not None else None,
            route_source=route.route_source if route is not None else None,
            prompt_packet_path=str(prompt_packet_path) if prompt_packet_path is not None else None,
            source_evidence_path=str(source_evidence_path) if source_evidence_path is not None else None,
            failure_reason=failure_reason,
            duration_ms=duration_ms,
            context_token_cost=context_bundle.token_cost,
            context_evidence_count=len(context_bundle.evidence_ids),
            context_duplicate_hits=context_bundle.duplicate_hits,
            context_memory_hits=context_bundle.memory_hits,
            evidence_ids=list(context_bundle.evidence_ids),
            budget_snapshot=dict(prompt_packet.budget_snapshot),
            usage=dict(response.usage) if response is not None else {},
            record_mode=record_mode,
            request_char_count=len(system_prompt) + len(user_prompt),
            system_prompt_chars=len(system_prompt),
            user_prompt_chars=len(user_prompt),
            response_chars=len(response_text),
            system_prompt_preview=self._clip_text(system_prompt, limit=260),
            user_prompt_preview=self._clip_text(user_prompt, limit=420),
            response_preview=self._clip_text(response_text, limit=420) if response_text else None,
            parsed_payload_keys=sorted(normalized_payload.keys()) if normalized_payload is not None else [],
            system_prompt=system_prompt if record_mode == "full" else None,
            user_prompt=user_prompt if record_mode == "full" else None,
            raw_response_text=response_text if record_mode == "full" and response_text else None,
            parsed_payload=normalized_payload if record_mode == "full" else None,
        )
        return self.interaction_logger.record(record, artifact_path=artifact_path)

    def _normalize_output(self, payload: dict[str, Any]) -> dict[str, Any]:
        """清洗模型输出，只保留允许回写的字段"""

        normalized: dict[str, Any] = {}
        for key in (
            "root_cause",
            "must_keep_conditions",
            "must_keep_side_effects",
            "critical_calls",
            "touched_files",
            "touched_functions",
        ):
            value = payload.get(key)
            if key == "root_cause":
                cleaned = self._clean_text(value)
                if cleaned:
                    normalized[key] = cleaned
                continue
            cleaned_list = self._clean_list(value)
            if cleaned_list:
                normalized[key] = cleaned_list
        return normalized

    def _merge_card(
        self,
        draft_card: SemanticCard,
        model_output: dict[str, Any],
    ) -> tuple[SemanticCard, list[str]]:
        """把模型输出按增量方式并回草稿卡片"""

        updates: dict[str, Any] = {}
        merged_fields: list[str] = []

        root_cause = model_output.get("root_cause")
        if root_cause and root_cause != draft_card.root_cause:
            updates["root_cause"] = root_cause
            merged_fields.append("root_cause")

        for field_name in (
            "must_keep_conditions",
            "must_keep_side_effects",
            "critical_calls",
            "touched_files",
            "touched_functions",
        ):
            current_values = list(getattr(draft_card, field_name))
            merged_values = self._merge_unique(current_values, model_output.get(field_name) or [])
            if merged_values != current_values:
                updates[field_name] = merged_values
                merged_fields.append(field_name)

        if not updates:
            return draft_card, merged_fields
        return draft_card.model_copy(update=updates), merged_fields

    def _merge_unique(self, current_values: list[str], new_values: list[str]) -> list[str]:
        """按顺序合并列表，并清理重复项"""

        result: list[str] = []
        seen: set[str] = set()
        for item in [*current_values, *new_values]:
            normalized = self._clean_text(item)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
        return result

    def _clean_list(self, value: Any) -> list[str]:
        """把模型输出规整成字符串列表"""

        if value is None:
            return []
        if isinstance(value, str):
            candidates = [part.strip() for part in re.split(r"[\n,;；]+", value) if part.strip()]
            return [item for item in (self._clean_text(part) for part in candidates) if item]
        if isinstance(value, list):
            return [item for item in (self._clean_text(part) for part in value) if item]
        return []

    def _clean_text(self, value: Any) -> str | None:
        """清理模型输出里的 Markdown 和多余空白"""

        if not isinstance(value, str):
            return None
        text = value.strip()
        if not text:
            return None
        text = text.replace("\\`", "`")
        text = text.strip("`")
        text = re.sub(r"^\s*[-*]\s*", "", text)
        text = re.sub(r"`([^`]*)`", r"\1", text)
        text = text.replace("`", "")
        text = re.sub(r"\s+", " ", text).strip()
        return text or None

    def _clip_text(self, text: str, *, limit: int) -> str:
        """裁剪长文本，避免提示过度膨胀"""

        compact = re.sub(r"\s+", " ", text).strip()
        if len(compact) <= limit:
            return compact
        return compact[: limit - 3].rstrip() + "..."
