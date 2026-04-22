from __future__ import annotations

import json
from pathlib import Path

from patchweaver.analyzer.semantic_enricher import SemanticCardEnricher
from patchweaver.config.models import ModelsConfig
from patchweaver.models.context import ContextBundle
from patchweaver.models.evidence import EvidenceSpan
from patchweaver.models.patch import PatchBundle, SourceEvidence
from patchweaver.models.prompt import PromptPacket
from patchweaver.models.semantic import SemanticCard
from patchweaver.models.skill import SkillRouteDecision
from patchweaver.models.task import TaskContext
from patchweaver.prompting.model_client import ChatJsonResult, ModelClientError


class _FakeChatClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def chat_json(self, *, model: str, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> ChatJsonResult:
        assert model
        assert "SemanticCard" in user_prompt
        return ChatJsonResult(
            payload=self.payload,
            raw_content=json.dumps(self.payload, ensure_ascii=False),
            response_id="resp-demo",
            model_name=model,
            usage={"prompt_tokens": 123, "completion_tokens": 45, "total_tokens": 168},
        )


class _FailingChatClient:
    def chat_json(self, *, model: str, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> ChatJsonResult:
        raise ModelClientError("mock timeout")


def _draft_card() -> SemanticCard:
    return SemanticCard(
        bug_class="cve_fix",
        root_cause="legacy_parse_param 中存在无符号算术导致的边界判断错误。",
        must_keep_conditions=["legacy_parse_param: size + len + 2 > PAGE_SIZE"],
        must_keep_side_effects=["legacy_parse_param: 条件 `size + len + 2 > PAGE_SIZE` 命中时返回 `invalf(...)`"],
        critical_calls=["invalf"],
        touched_files=["fs/fs_context.c"],
        touched_functions=["legacy_parse_param"],
    )


def _task(tmp_path: Path) -> TaskContext:
    return TaskContext(
        task_id="semantic-enrich-001",
        cve_id="CVE-2022-0185",
        target_kernel="6.6.102-5.2.an23.x86_64",
        workspace_dir=tmp_path,
    )


def _bundle() -> PatchBundle:
    return PatchBundle(
        task_id="semantic-enrich-001",
        cve_id="CVE-2022-0185",
        commit_message="vfs: fs_context: fix up param length parsing in legacy_parse_param",
        affected_files=["fs/fs_context.c"],
        source_evidence=[
            SourceEvidence(
                source_name="nvd",
                url="https://example.invalid/nvd",
                summary="A heap-based buffer overflow flaw was found in the way the legacy_parse_param function verified the supplied parameters length.",
                stage="metadata",
                preferred=True,
            )
        ],
    )


def _prompt_packet() -> PromptPacket:
    return PromptPacket(
        stage_name="semantic_card",
        system_prompt_version="v1",
        worker_prompt_version="v1",
        schema_name="SemanticCard",
        prompt_sections=[
            "你负责抽取最小修复语义边界。",
            "输出需满足 SemanticCard 对应的结构约束。",
            "阶段: semantic_card",
        ],
    )


def _context_bundle() -> ContextBundle:
    return ContextBundle(
        evidence_ids=["ANL-01"],
        token_cost=128,
        source_spans=[
            EvidenceSpan(
                evidence_id="ANL-01",
                source_type="json",
                source_path="workspaces/demo/input/patch_bundle.json",
                excerpt='{"commit_message":"fix up param length parsing"}',
                start_line=1,
                end_line=8,
                score=1.0,
            )
        ],
        notes=["证据片段数: 1"],
    )


def _route() -> SkillRouteDecision:
    return SkillRouteDecision(
        stage_name="semantic_card",
        selected_skill="semantic_card",
        selection_reason="命中 project semantic skill。",
        contract_summary=["输出: semantic_card.json"],
    )


def test_semantic_enricher_merges_model_output(tmp_path: Path) -> None:
    enricher = SemanticCardEnricher(
        ModelsConfig(api_key="sk-test"),
        project_root=tmp_path,
        chat_client=_FakeChatClient(
            {
                "root_cause": "legacy_parse_param 中的长度累加检查原先存在无符号下溢风险，修复通过显式累加 size、len 和常量边界避免越界。",
                "must_keep_conditions": ["legacy_parse_param: size + len + 2 > PAGE_SIZE"],
                "must_keep_side_effects": [
                    "legacy_parse_param: 当 size + len + 2 > PAGE_SIZE 时返回 invalf(fc, \"VFS: Legacy: Cumulative options too large\")",
                    "legacy_parse_param: 保持对累计挂载参数长度的拒绝路径",
                ],
                "critical_calls": ["invalf", "strchr"],
                "touched_files": ["fs/fs_context.c"],
                "touched_functions": ["legacy_parse_param"],
            }
        ),
    )

    merged_card, trace = enricher.enrich(
        task=_task(tmp_path),
        patch_bundle=_bundle(),
        draft_card=_draft_card(),
        prompt_packet=_prompt_packet(),
        context_bundle=_context_bundle(),
        route=_route(),
        patch_text="if (size + len + 2 > PAGE_SIZE) return invalf(...);",
        prompt_packet_path=tmp_path / "analysis" / "prompt" / "semantic_card_prompt_packet.json",
        source_evidence_path=tmp_path / "input" / "source_evidence.json",
    )

    assert trace.status == "applied"
    assert trace.applied is True
    assert trace.record_mode == "basic"
    assert "root_cause" in trace.merged_fields
    assert "critical_calls" in trace.merged_fields
    assert merged_card.root_cause.startswith("legacy_parse_param 中的长度累加检查")
    assert merged_card.critical_calls == ["invalf", "strchr"]
    assert merged_card.touched_files == ["fs/fs_context.c"]
    assert merged_card.must_keep_side_effects == [
        "legacy_parse_param: 当 size + len + 2 > PAGE_SIZE 时返回 invalf(fc, \"VFS: Legacy: Cumulative options too large\")",
        "legacy_parse_param: 保持对累计挂载参数长度的拒绝路径",
    ]
    assert trace.interaction_record_path == "analysis/trace/semantic_card_model_interaction.json"

    interaction_path = tmp_path / "analysis" / "trace" / "semantic_card_model_interaction.json"
    assert interaction_path.exists()
    interaction_payload = json.loads(interaction_path.read_text(encoding="utf-8"))
    assert interaction_payload["context_token_cost"] == 128
    assert interaction_payload["context_evidence_count"] == 1
    assert interaction_payload["record_mode"] == "basic"
    assert interaction_payload["system_prompt"] is None
    assert interaction_payload["user_prompt"] is None
    assert interaction_payload["raw_response_text"] is None
    assert interaction_payload["system_prompt_preview"]
    assert interaction_payload["response_preview"]
    assert interaction_payload["parsed_payload_keys"] == [
        "critical_calls",
        "must_keep_conditions",
        "must_keep_side_effects",
        "root_cause",
        "touched_files",
        "touched_functions",
    ]

    interaction_jsonl = tmp_path / "data" / "logs" / "model_interactions.jsonl"
    assert interaction_jsonl.exists()
    jsonl_records = [json.loads(line) for line in interaction_jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(jsonl_records) == 1
    assert jsonl_records[0]["task_id"] == "semantic-enrich-001"
    assert jsonl_records[0]["usage"]["total_tokens"] == 168


def test_semantic_enricher_prefers_more_specific_side_effect_text() -> None:
    enricher = SemanticCardEnricher(models_config=None)

    merged = enricher._merge_side_effects(
        ["legacy_parse_param: 条件 size + len + 2 > PAGE_SIZE 命中时返回 invalf(...)"],
        ["legacy_parse_param: 当 size + len + 2 > PAGE_SIZE 时返回 invalf(fc, \"VFS: Legacy: Cumulative options too large\")"],
    )

    assert merged == [
        "legacy_parse_param: 当 size + len + 2 > PAGE_SIZE 时返回 invalf(fc, \"VFS: Legacy: Cumulative options too large\")"
    ]


def test_semantic_side_effect_key_matches_equivalent_return_paths() -> None:
    enricher = SemanticCardEnricher(models_config=None)

    current_key = enricher._semantic_item_key(
        "must_keep_side_effects",
        "legacy_parse_param: 条件 size + len + 2 > PAGE_SIZE 命中时返回 invalf(...)",
    )
    enriched_key = enricher._semantic_item_key(
        "must_keep_side_effects",
        "legacy_parse_param: 当 size + len + 2 > PAGE_SIZE 时返回 invalf(fc, \"VFS: Legacy: Cumulative options too large\")",
    )

    assert current_key == enriched_key


def test_semantic_enricher_skips_without_api_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("PATCHWEAVER_BAILIAN_API_KEY", raising=False)
    enricher = SemanticCardEnricher(ModelsConfig(api_key=""))

    merged_card, trace = enricher.enrich(
        task=_task(tmp_path),
        patch_bundle=_bundle(),
        draft_card=_draft_card(),
        prompt_packet=_prompt_packet(),
        context_bundle=_context_bundle(),
        route=_route(),
        patch_text="if (size + len + 2 > PAGE_SIZE) return invalf(...);",
        prompt_packet_path=tmp_path / "analysis" / "prompt" / "semantic_card_prompt_packet.json",
        source_evidence_path=tmp_path / "input" / "source_evidence.json",
    )

    assert merged_card == _draft_card()
    assert trace.status == "skipped"
    assert "PATCHWEAVER_BAILIAN_API_KEY" in (trace.reason or "")


def test_semantic_enricher_full_record_mode_persists_full_prompts(tmp_path: Path) -> None:
    enricher = SemanticCardEnricher(
        ModelsConfig(api_key="sk-test", interaction_record_mode="full"),
        project_root=tmp_path,
        chat_client=_FakeChatClient(
            {
                "root_cause": "legacy_parse_param 需要保留累加后的边界判断。",
                "must_keep_conditions": ["legacy_parse_param: size + len + 2 > PAGE_SIZE"],
                "must_keep_side_effects": ["legacy_parse_param: 条件命中时返回 invalf(...)"],
                "critical_calls": ["invalf"],
                "touched_files": ["fs/fs_context.c"],
                "touched_functions": ["legacy_parse_param"],
            }
        ),
    )

    _, trace = enricher.enrich(
        task=_task(tmp_path),
        patch_bundle=_bundle(),
        draft_card=_draft_card(),
        prompt_packet=_prompt_packet(),
        context_bundle=_context_bundle(),
        route=_route(),
        patch_text="if (size + len + 2 > PAGE_SIZE) return invalf(...);",
        prompt_packet_path=tmp_path / "analysis" / "prompt" / "semantic_card_prompt_packet.json",
        source_evidence_path=tmp_path / "input" / "source_evidence.json",
    )

    interaction_path = tmp_path / "analysis" / "trace" / "semantic_card_model_interaction.json"
    payload = json.loads(interaction_path.read_text(encoding="utf-8"))
    assert trace.record_mode == "full"
    assert payload["record_mode"] == "full"
    assert "semantic_card 阶段补全器" in payload["system_prompt"]
    assert "请依据下面的输入补全 SemanticCard" in payload["user_prompt"]
    assert payload["raw_response_text"]
    assert payload["parsed_payload"]["root_cause"] == "legacy_parse_param 需要保留累加后的边界判断。"


def test_semantic_enricher_records_failure_with_structured_event(tmp_path: Path) -> None:
    enricher = SemanticCardEnricher(
        ModelsConfig(api_key="sk-test"),
        project_root=tmp_path,
        chat_client=_FailingChatClient(),
    )

    merged_card, trace = enricher.enrich(
        task=_task(tmp_path),
        patch_bundle=_bundle(),
        draft_card=_draft_card(),
        prompt_packet=_prompt_packet(),
        context_bundle=_context_bundle(),
        route=_route(),
        patch_text="if (size + len + 2 > PAGE_SIZE) return invalf(...);",
        prompt_packet_path=tmp_path / "analysis" / "prompt" / "semantic_card_prompt_packet.json",
        source_evidence_path=tmp_path / "input" / "source_evidence.json",
    )

    assert merged_card == _draft_card()
    assert trace.status == "failed"
    assert trace.interaction_record_path == "analysis/trace/semantic_card_model_interaction.json"

    interaction_path = tmp_path / "analysis" / "trace" / "semantic_card_model_interaction.json"
    payload = json.loads(interaction_path.read_text(encoding="utf-8"))
    assert payload["success"] is False
    assert payload["status"] == "failed"
    assert payload["failure_reason"] == "模型补全失败: mock timeout"
    assert payload["usage"] == {}
