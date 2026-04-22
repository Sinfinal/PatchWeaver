"""OpenAI 兼容模型调用客户端"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any
from urllib import error, request


class ModelClientError(RuntimeError):
    """表示模型调用或返回解析失败"""


@dataclass(slots=True)
class ChatJsonResult:
    """表示一次 JSON 聊天补全的结果"""

    payload: dict[str, Any]
    raw_content: str
    response_id: str | None = None
    model_name: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)


class OpenAICompatibleChatClient:
    """负责调用 OpenAI 兼容的聊天补全接口"""

    def __init__(self, *, base_url: str, api_key: str, timeout_sec: int = 45) -> None:
        """保存接口地址和鉴权信息"""

        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_sec = timeout_sec

    def chat_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
    ) -> ChatJsonResult:
        """请求模型并解析出 JSON 对象"""

        endpoint = f"{self.base_url}/chat/completions"
        body = {
            "model": model,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            endpoint,
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )

        try:
            with request.urlopen(req, timeout=self.timeout_sec) as response:
                raw_text = response.read().decode("utf-8")
        except error.HTTPError as exc:  # pragma: no cover - 真实网络失败分支
            detail = exc.read().decode("utf-8", errors="replace")
            raise ModelClientError(f"模型接口返回 HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:  # pragma: no cover - 真实网络失败分支
            raise ModelClientError(f"模型接口访问失败: {exc.reason}") from exc

        try:
            response_payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ModelClientError("模型接口返回了无法解析的 JSON 响应。") from exc

        raw_content = self._extract_message_content(response_payload)
        parsed_payload = self._extract_json_object(raw_content)
        return ChatJsonResult(
            payload=parsed_payload,
            raw_content=raw_content,
            response_id=response_payload.get("id"),
            model_name=response_payload.get("model"),
            usage=response_payload.get("usage") or {},
        )

    def _extract_message_content(self, response_payload: dict[str, Any]) -> str:
        """从兼容响应中提取首条消息内容"""

        choices = response_payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ModelClientError("模型接口响应缺少 choices。")

        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise ModelClientError("模型接口响应缺少 message。")

        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            text_parts = [
                str(item.get("text", "")).strip()
                for item in content
                if isinstance(item, dict) and item.get("type") in {None, "text"}
            ]
            joined = "\n".join(part for part in text_parts if part)
            if joined:
                return joined
        raise ModelClientError("模型接口响应缺少可读的 content。")

    def _extract_json_object(self, raw_content: str) -> dict[str, Any]:
        """从消息文本中解析出 JSON 对象"""

        text = raw_content.strip()
        if text.startswith("```"):
            text = self._strip_code_fence(text)

        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1 or start >= end:
                raise ModelClientError("模型返回内容中没有可解析的 JSON 对象。") from None
            try:
                payload = json.loads(text[start : end + 1])
            except json.JSONDecodeError as exc:
                raise ModelClientError("模型返回了 JSON 片段，但解析失败。") from exc

        if not isinstance(payload, dict):
            raise ModelClientError("模型返回的 JSON 顶层不是对象。")
        return payload

    def _strip_code_fence(self, text: str) -> str:
        """移除 Markdown 代码块包装"""

        stripped = text.strip()
        if not stripped.startswith("```"):
            return stripped
        lines = stripped.splitlines()
        if len(lines) >= 2 and lines[-1].strip().startswith("```"):
            return "\n".join(lines[1:-1]).strip()
        return stripped
