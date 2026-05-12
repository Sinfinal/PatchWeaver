"""Short LLM-backed failure explanations for Web task lists."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from patchweaver.config.models import ModelsConfig
from patchweaver.prompting.model_client import ModelClientError, OpenAICompatibleChatClient

_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|password|passwd|credential|secret)\s*[:=]\s*[^ \n\r\t]+"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
]

_FALLBACK_EXPLANATIONS: dict[str, str] = {
    "build_cache_incomplete": "构建缓存缺失",
    "build_env_missing": "构建环境缺依赖",
    "compile_failed": "编译阶段失败",
    "dependency_gap": "模块依赖缺失",
    "ineffective_retry": "重试策略无效",
    "kernel_config_missing": "内核配置缺失",
    "kernel_src_missing": "内核源码缺失",
    "kpatch_constraint": "kpatch不支持此改动",
    "kpatch_section_symbol_offset_constraint": "符号偏移受限",
    "kpatch_symbol_bundle_constraint": "符号打包受限",
    "module_load_failed": "模块加载失败",
    "patch_apply_failed": "补丁上下文不匹配",
    "source_unavailable": "CVE来源不可用",
    "target_already_patched": "目标已含修复",
    "validation_failed": "动态验证失败",
    "vmlinux_missing": "vmlinux缺失",
    "unknown": "失败原因待确认",
}


class FailureExplanationOutput(BaseModel):
    """Structured output returned by the failure explanation model."""

    explanation: str


class FailureExplanationService:
    """Generate concise Chinese explanations for failure types."""

    def __init__(
        self,
        *,
        models_config: ModelsConfig | None = None,
        chat_client: OpenAICompatibleChatClient | None = None,
        prompt_path: Path | None = None,
    ) -> None:
        self.models_config = models_config
        self.chat_client = chat_client or self._build_default_client(models_config)
        self.prompt_path = prompt_path or Path(__file__).resolve().parents[2] / "agent" / "prompts" / "failure_explanation_system.md"

    def explain(
        self,
        *,
        failure_type: str | None,
        summary: str | None = None,
        diagnostics: dict[str, Any] | None = None,
        task_workspace: Path | None = None,
    ) -> dict[str, Any]:
        """Return a short explanation and metadata about its source."""

        normalized_type = (failure_type or "unknown").strip() or "unknown"
        normalized_summary = (summary or "").strip()
        cache_key = self._cache_key(
            failure_type=normalized_type,
            summary=normalized_summary,
            diagnostics=diagnostics or {},
        )
        cache_path = self._cache_path(task_workspace)
        cached = self._read_cache(cache_path, cache_key=cache_key)
        if cached is not None:
            return cached

        if self.chat_client is None:
            return self._write_cache(
                cache_path,
                payload=self._fallback_payload(
                    failure_type=normalized_type,
                    reason="missing_model_client",
                    cache_key=cache_key,
                ),
            )

        try:
            response = self.chat_client.chat_json(
                model=self._model_name(),
                system_prompt=self._system_prompt(),
                user_prompt=self._user_prompt(
                    failure_type=normalized_type,
                    summary=normalized_summary,
                    diagnostics=diagnostics or {},
                ),
                temperature=0.0,
            )
            output = FailureExplanationOutput.model_validate(response.payload)
            explanation = self._normalize_explanation(output.explanation)
            if not explanation:
                raise ValueError("empty explanation")
            return self._write_cache(
                cache_path,
                payload={
                    "failure_type": normalized_type,
                    "summary_hash": cache_key,
                    "explanation": explanation,
                    "source": "llm",
                    "model_name": response.model_name or self._model_name(),
                    "input_redacted": True,
                    "full_log_sent": False,
                },
            )
        except (ModelClientError, ValidationError, ValueError, TypeError, OSError) as exc:
            return self._write_cache(
                cache_path,
                payload=self._fallback_payload(
                    failure_type=normalized_type,
                    reason=f"llm_unavailable: {exc}",
                    cache_key=cache_key,
                ),
            )

    def _fallback_payload(self, *, failure_type: str, reason: str, cache_key: str) -> dict[str, Any]:
        return {
            "failure_type": failure_type,
            "summary_hash": cache_key,
            "explanation": _FALLBACK_EXPLANATIONS.get(failure_type, _FALLBACK_EXPLANATIONS["unknown"]),
            "source": "fallback_rule",
            "fallback_reason": reason,
            "input_redacted": True,
            "full_log_sent": False,
        }

    def _system_prompt(self) -> str:
        if self.prompt_path.exists():
            return self.prompt_path.read_text(encoding="utf-8")
        return (
            "You explain PatchWeaver failure types for a Web table. Return one JSON object "
            "with explanation. The explanation must be concise Simplified Chinese, <=12 Chinese characters, no punctuation."
        )

    def _user_prompt(self, *, failure_type: str, summary: str, diagnostics: dict[str, Any]) -> str:
        payload = {
            "failure_type": failure_type,
            "failure_summary": self._clip_text(self._redact_text(summary), 400),
            "diagnostics": self._clip_payload(self._redact_payload(diagnostics), 1200),
            "output_contract": {
                "explanation": "简体中文短语，最多 12 个汉字或 18 个中英文字符，不加标点，不声称已修复",
            },
            "examples": {
                "build_env_missing": "构建环境缺依赖",
                "kpatch_constraint": "kpatch不支持此改动",
                "patch_apply_failed": "补丁上下文不匹配",
            },
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def _read_cache(self, cache_path: Path | None, *, cache_key: str) -> dict[str, Any] | None:
        if cache_path is None or not cache_path.exists():
            return None
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        if payload.get("summary_hash") != cache_key:
            return None
        explanation = str(payload.get("explanation") or "").strip()
        if not explanation:
            return None
        return payload

    def _write_cache(self, cache_path: Path | None, *, payload: dict[str, Any]) -> dict[str, Any]:
        if cache_path is not None:
            try:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            except OSError:
                pass
        return payload

    def _cache_path(self, task_workspace: Path | None) -> Path | None:
        if task_workspace is None:
            return None
        return Path(task_workspace) / "agent" / "failure_explanation.json"

    def _cache_key(self, *, failure_type: str, summary: str, diagnostics: dict[str, Any]) -> str:
        payload = {
            "failure_type": failure_type,
            "summary": self._redact_text(summary),
            "diagnostics": self._clip_payload(self._redact_payload(diagnostics), 1200),
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _normalize_explanation(self, value: str) -> str:
        text = re.sub(r"[\s。！？；;,.，、]+", "", str(value or "").strip())
        return text[:18]

    def _model_name(self) -> str:
        if self.models_config is None:
            return "unknown"
        return self.models_config.helper_models.get("log_summary") or self.models_config.development_model or self.models_config.default_model

    def _build_default_client(self, models_config: ModelsConfig | None) -> OpenAICompatibleChatClient | None:
        if models_config is None:
            return None
        if models_config.endpoint_mode != "openai_compatible":
            return None
        api_key = models_config.resolve_api_key()
        if not api_key:
            return None
        return OpenAICompatibleChatClient(base_url=models_config.base_url, api_key=api_key, timeout_sec=15)

    def _redact_text(self, text: str) -> str:
        redacted = text
        for pattern in _SECRET_PATTERNS:
            redacted = pattern.sub(lambda match: f"{match.group(1) if match.groups() else 'secret'}[REDACTED]", redacted)
        return redacted

    def _redact_payload(self, value: Any) -> Any:
        if isinstance(value, str):
            return self._redact_text(value)
        if isinstance(value, dict):
            return {str(key): self._redact_payload(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._redact_payload(item) for item in value]
        if isinstance(value, tuple):
            return [self._redact_payload(item) for item in value]
        return value

    def _clip_text(self, text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[:limit] + f"\n...[truncated {len(text) - limit} chars]..."

    def _clip_payload(self, payload: Any, limit: int) -> Any:
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if len(text) <= limit:
            return payload
        return {"truncated_json_excerpt": self._clip_text(text, limit)}
