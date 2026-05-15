"""Reflection memory helpers for the autonomous Agent loop."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from patchweaver.agent.planning_contracts import ReflectionRecord, TaskPlan, ToolResult
from patchweaver.agent.state import AgentObservation, sanitize_agent_payload
from patchweaver.config.models import ModelsConfig
from patchweaver.memory.dual_memory import DualMemory
from patchweaver.models.attempt import FailureRecord
from patchweaver.models.task import TaskContext
from patchweaver.prompting.model_client import ModelClientError, OpenAICompatibleChatClient

REFLECTION_FILE_NAME = "reflection.json"
TERMINAL_FAILURE_TYPES = {
    "source_unavailable",
    "build_env_missing",
    "kernel_src_missing",
    "kernel_config_missing",
    "vmlinux_missing",
    "build_cache_incomplete",
}
GENERIC_NEXT_STRATEGY_HINTS = {
    "stop_manual_review 或选择有证据的替代策略",
}
SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|password|passwd|credential|secret)\s*[:=]\s*[^ \n\r\t]+"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
]


class LLMReflectionOutput(BaseModel):
    """Structured output returned by the reflection model."""

    what_to_avoid: str
    next_strategy_hint: str


def generate_reflection(
    observation: AgentObservation,
    tool_result: ToolResult | None = None,
    *,
    models_config: ModelsConfig | None = None,
    chat_client: OpenAICompatibleChatClient | None = None,
) -> ReflectionRecord:
    """Generate structured failure memory from the latest Agent observation."""

    failure_type = observation.failure_type or "unknown"
    attempt_no = observation.latest_attempt_no or observation.current_attempt or None
    disabled_strategies = _disabled_strategies(observation)
    evidence_refs = _merge_evidence(observation, tool_result)
    what_to_avoid = _what_to_avoid(failure_type=failure_type, disabled_strategies=disabled_strategies)
    next_strategy_hint = _next_strategy_hint(observation)
    reflection_mode = "rule"
    if _needs_llm_reflection(failure_type=failure_type, next_strategy_hint=next_strategy_hint):
        try:
            llm_output = _generate_llm_reflection(
                observation=observation,
                tool_result=tool_result,
                failure_type=failure_type,
                disabled_strategies=disabled_strategies,
                models_config=models_config,
                chat_client=chat_client,
            )
            if llm_output is not None:
                what_to_avoid = llm_output.what_to_avoid or what_to_avoid
                next_strategy_hint = llm_output.next_strategy_hint or next_strategy_hint
                reflection_mode = "llm"
            else:
                reflection_mode = "fallback_rule"
        except (ModelClientError, ValidationError, ValueError, OSError, TypeError):
            reflection_mode = "fallback_rule"

    return ReflectionRecord(
        reflection_id=_reflection_id(attempt_no=attempt_no, failure_type=failure_type),
        attempt_no=attempt_no,
        failure_type=failure_type,
        what_failed=_what_failed(observation, tool_result),
        what_to_avoid=what_to_avoid,
        next_strategy_hint=next_strategy_hint,
        evidence_refs=evidence_refs,
        disabled_strategies=disabled_strategies,
        terminal=failure_type in TERMINAL_FAILURE_TYPES,
        reflection_mode=reflection_mode,
    )


def _needs_llm_reflection(*, failure_type: str, next_strategy_hint: str) -> bool:
    return failure_type == "unknown" or next_strategy_hint in GENERIC_NEXT_STRATEGY_HINTS


def _generate_llm_reflection(
    *,
    observation: AgentObservation,
    tool_result: ToolResult | None,
    failure_type: str,
    disabled_strategies: list[str],
    models_config: ModelsConfig | None,
    chat_client: OpenAICompatibleChatClient | None,
) -> LLMReflectionOutput | None:
    client = chat_client or _build_reflection_client(models_config)
    if client is None:
        return None
    response = client.chat_json(
        model=_reflection_model_name(models_config),
        system_prompt=_reflection_system_prompt(),
        user_prompt=_reflection_user_prompt(
            observation=observation,
            tool_result=tool_result,
            failure_type=failure_type,
            disabled_strategies=disabled_strategies,
        ),
        temperature=0.0,
    )
    return LLMReflectionOutput.model_validate(response.payload)


def save_reflection(
    reflection: ReflectionRecord,
    task_workspace: Path,
    *,
    memory: DualMemory | None = None,
    task: TaskContext | None = None,
    failure_record: FailureRecord | None = None,
    recipe_name: str | None = None,
    candidate_id: str | None = None,
) -> Path:
    """Persist a task-local reflection and optionally mirror it into DualMemory."""

    path = Path(task_workspace) / REFLECTION_FILE_NAME
    reflections = _load_reflection_file(path)
    by_id = {
        _effective_reflection_id(item): item
        for item in reflections
    }
    by_id[_effective_reflection_id(reflection)] = reflection
    ordered = sorted(
        by_id.values(),
        key=lambda item: (item.attempt_no is None, item.attempt_no or 0, item.failure_type),
    )
    payload = {
        "latest": reflection.model_dump(mode="json"),
        "reflections": [item.model_dump(mode="json") for item in ordered],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(sanitize_agent_payload(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if memory is not None:
        memory.record_reflection(
            reflection,
            task=task,
            failure_record=failure_record,
            recipe_name=recipe_name,
            candidate_id=candidate_id,
        )
    return path


def load_reflections_for_next_attempt(
    task_workspace: Path,
    memory: DualMemory | None = None,
    *,
    limit: int = 8,
    cve_id: str | None = None,
) -> list[ReflectionRecord]:
    """Load task-local and memory-backed reflections for the next Planner call."""

    local = _load_reflection_file(Path(task_workspace) / REFLECTION_FILE_NAME)
    memory_reflections = memory.load_reflections(limit=limit, cve_id=cve_id) if memory is not None else []
    merged: dict[str, ReflectionRecord] = {}
    for reflection in [*memory_reflections, *local]:
        merged[_effective_reflection_id(reflection)] = reflection
    return sorted(
        merged.values(),
        key=lambda item: (item.attempt_no is None, item.attempt_no or 0, item.failure_type),
        reverse=True,
    )[:limit]


def build_memory_hints_from_reflections(reflections: list[ReflectionRecord]) -> list[dict[str, Any]]:
    """Convert reflection records into AgentObservation memory hints."""

    hints: list[dict[str, Any]] = []
    for reflection in reflections:
        disabled = bool(reflection.disabled_strategies)
        hint = {
            "kind": "reflection",
            "reflection_id": _effective_reflection_id(reflection),
            "failure_type": reflection.failure_type,
            "status": "ineffective_retry" if disabled else "terminal" if reflection.terminal else "available",
            "terminal": reflection.terminal,
            "disabled": disabled,
            "disabled_strategies": list(reflection.disabled_strategies),
            "strategy": reflection.disabled_strategies[0] if reflection.disabled_strategies else None,
            "what_to_avoid": reflection.what_to_avoid,
            "next_strategy_hint": reflection.next_strategy_hint,
            "evidence_refs": list(reflection.evidence_refs),
        }
        hints.append(sanitize_agent_payload(hint))
    return hints


def mark_memory_usage(
    *,
    tool_result: ToolResult,
    plan: TaskPlan,
    reflections: list[ReflectionRecord],
) -> ToolResult:
    """Flag a tool result when a plan ignored available reflection memory."""

    metadata = dict(tool_result.metadata)
    if reflections and not plan.used_reflections:
        metadata["memory_not_used"] = True
        metadata["available_reflection_count"] = len(reflections)
        metadata["available_reflection_ids"] = [_effective_reflection_id(item) for item in reflections]
    else:
        metadata["memory_not_used"] = False
    return tool_result.model_copy(update={"metadata": sanitize_agent_payload(metadata)})


def _load_reflection_file(path: Path) -> list[ReflectionRecord]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError):
        return []
    raw = payload.get("reflections") if isinstance(payload, dict) else payload
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    reflections: list[ReflectionRecord] = []
    for item in raw:
        try:
            reflections.append(ReflectionRecord.model_validate(item))
        except ValueError:
            continue
    return reflections


def _reflection_id(*, attempt_no: int | None, failure_type: str) -> str:
    attempt_text = attempt_no if attempt_no is not None else "unknown"
    normalized_failure = re.sub(r"[^A-Za-z0-9_.-]+", "-", failure_type).strip("-") or "unknown"
    return f"reflection-{attempt_text}-{normalized_failure}"


def _effective_reflection_id(reflection: ReflectionRecord) -> str:
    return reflection.reflection_id or _reflection_id(
        attempt_no=reflection.attempt_no,
        failure_type=reflection.failure_type,
    )


def _merge_evidence(observation: AgentObservation, tool_result: ToolResult | None) -> list[str]:
    evidence = list(observation.evidence_refs)
    if tool_result is not None:
        evidence.extend(tool_result.artifact_paths)
        if tool_result.error:
            evidence.append(tool_result.error)
    return list(dict.fromkeys(str(item) for item in evidence if item))[:8]


def _what_failed(observation: AgentObservation, tool_result: ToolResult | None) -> str:
    failure_type = observation.failure_type or "unknown"
    summary = observation.failure_summary or ""
    if tool_result is not None and tool_result.error:
        summary = summary or tool_result.error
    if not summary:
        summary = observation.latest_status or observation.task_status
    return f"{failure_type}: {summary}"


def _what_to_avoid(*, failure_type: str, disabled_strategies: list[str]) -> str:
    if failure_type == "source_unavailable":
        return "不要消耗 attempt 或进入构建链路，先补来源映射或更换有明确修复提交的 CVE"
    if failure_type == "patch_apply_failed":
        return "不要在未对齐未修复源码基线时继续强行 apply 或 build"
    if failure_type in {"build_env_missing", "build_cache_incomplete"}:
        return "不要继续构建，先修复 kpatch、debug vmlinux、Module.symvers 或源码构建缓存"
        if disabled_strategies:
            return "不要重复使用已无效策略：" + ",".join(disabled_strategies)
        return "不要重复直接套用同一改写形态，必须切换 livepatch 约束规避路线"
    return "不要重复上一轮无证据收益的策略，先基于失败归因重新规划"


def _next_strategy_hint(observation: AgentObservation) -> str:
    failure_type = observation.failure_type or "unknown"
    if failure_type == "source_unavailable":
        return "terminal=true; stop_manual_review; 补来源映射或更换有明确修复提交的 CVE"
    if failure_type in {"build_env_missing", "build_cache_incomplete"}:
        return "系统将自动创建可写构建树后重试；若仍失败则检查磁盘空间或 Docker 挂载"
    if failure_type == "patch_apply_failed":
        subtype = _diagnostic_path(observation.diagnostics, "patch_apply", "subtype")
        if subtype in {"context_mismatch", "source_too_new_or_already_patched"}:
            return "stable_source_baseline + reverse_unpatch + context_adapter"
        return "stable_source_baseline + apply_precheck_repair"
    if failure_type == "kpatch_constraint":
        next_strategy = _diagnostic_path(
            observation.diagnostics,
            "kpatch_constraint",
            "rewrite_classification",
            "next_strategy",
        )
        if isinstance(next_strategy, str) and next_strategy:
            return next_strategy
        return "section_change_avoidance + semantic_guard_rewrite"
    return "stop_manual_review 或选择有证据的替代策略"


def _disabled_strategies(observation: AgentObservation) -> list[str]:
    strategies: list[str] = []
    route = observation.diagnostics.get("route_effectiveness")
    if isinstance(route, dict):
        for key in ("selected_recipe", "recipe", "route_name", "strategy"):
            value = route.get(key)
            if isinstance(value, str) and value:
                strategies.append(value)
    for hint in observation.memory_hints:
        if not isinstance(hint, dict):
            continue
        for key in ("strategy", "selected_strategy", "recipe", "route_name"):
            value = hint.get(key)
            if isinstance(value, str) and value:
                strategies.append(value)
        disabled = hint.get("disabled_strategies")
        if isinstance(disabled, list):
            strategies.extend(str(item) for item in disabled if item)
    if observation.failure_type == "kpatch_constraint" and not strategies:
        strategies.append("direct_apply_patch")
    return list(dict.fromkeys(str(item) for item in strategies if item))


def _diagnostic_path(payload: dict[str, Any], *path: str) -> Any:
    value: Any = payload
    for part in path:
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _reflection_system_prompt() -> str:
    prompt_path = Path(__file__).resolve().parent / "prompts" / "reflection_system.md"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    return (
        "You are PatchWeaver's reflection generator. Return one JSON object with "
        "what_to_avoid and next_strategy_hint. Never include secrets or claim .ko success."
    )


def _reflection_user_prompt(
    *,
    observation: AgentObservation,
    tool_result: ToolResult | None,
    failure_type: str,
    disabled_strategies: list[str],
) -> str:
    payload = {
        "failure_type": failure_type,
        "failure_summary": _redact_text(observation.failure_summary or "") or None,
        "stage": observation.stage,
        "latest_status": observation.latest_status,
        "diagnostics": _redact_payload(observation.diagnostics),
        "disabled_strategies": disabled_strategies,
        "sanitized_build_log_excerpt": _build_log_excerpt(observation, tool_result),
        "tool_result": _redact_payload(tool_result.model_dump(mode="json")) if tool_result is not None else None,
        "output_contract": {
            "what_to_avoid": "one concrete sentence describing a strategy or action to avoid next",
            "next_strategy_hint": "one concrete next action hint for Planner, not a success claim",
        },
        "privacy_constraints": {
            "full_build_log_sent": False,
            "max_excerpt_chars": 800,
            "secrets_redacted": True,
        },
    }
    return json.dumps(sanitize_agent_payload(payload), ensure_ascii=False, sort_keys=True)


def _build_log_excerpt(observation: AgentObservation, tool_result: ToolResult | None) -> str:
    candidate = _diagnostic_path(observation.diagnostics, "build_log_excerpt")
    if isinstance(candidate, str) and candidate.strip():
        return _clip_text(_redact_text(candidate), 800)
    candidate = _diagnostic_path(observation.diagnostics, "log_excerpt")
    if isinstance(candidate, str) and candidate.strip():
        return _clip_text(_redact_text(candidate), 800)
    if tool_result is not None and tool_result.error:
        return _clip_text(_redact_text(tool_result.error), 800)
    for ref in observation.evidence_refs:
        path = Path(str(ref))
        if path.exists() and path.is_file():
            try:
                return _clip_text(_redact_text(_read_text_prefix(path, 2400)), 800)
            except OSError:
                continue
    summary = observation.failure_summary or observation.latest_status or observation.task_status
    return _clip_text(_redact_text(str(summary or "")), 800)


def _read_text_prefix(path: Path, limit: int) -> str:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return handle.read(limit)


def _redact_text(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(lambda match: f"{match.group(1) if match.groups() else 'secret'}[REDACTED]", redacted)
    return redacted


def _redact_payload(value: Any) -> Any:
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, dict):
        return {str(key): _redact_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_payload(item) for item in value]
    if isinstance(value, tuple):
        return [_redact_payload(item) for item in value]
    return value


def _clip_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncated {len(text) - limit} chars]..."


def _reflection_model_name(models_config: ModelsConfig | None) -> str:
    if models_config is None:
        return "unknown"
    return models_config.helper_models.get("log_summary") or models_config.development_model or models_config.default_model


def _build_reflection_client(models_config: ModelsConfig | None) -> OpenAICompatibleChatClient | None:
    if models_config is None:
        return None
    if models_config.endpoint_mode != "openai_compatible":
        return None
    api_key = models_config.resolve_api_key()
    if not api_key:
        return None
    return OpenAICompatibleChatClient(base_url=models_config.base_url, api_key=api_key)
