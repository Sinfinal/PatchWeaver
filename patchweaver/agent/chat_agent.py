"""Lightweight read-only Chat Agent for the Web console."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from patchweaver.api.deps import ApiContext
from patchweaver.api.schemas.chat import ChatResponse, SuggestedAction, ToolCallTrace
from patchweaver.agent import chat_tools
from patchweaver.prompting.model_client import ModelClientError, OpenAICompatibleChatClient

_sessions: dict[str, list[dict[str, str]]] = {}


class ChatAgent:
    """A bounded tool loop that answers Web operations questions without mutating state."""

    MAX_TOOL_ROUNDS = 3

    def __init__(self, context: ApiContext, chat_client: OpenAICompatibleChatClient | None = None) -> None:
        self.context = context
        self.models_config = getattr(context, "models_config", None)
        self.chat_client = chat_client if chat_client is not None else self._build_chat_client()
        self.system_prompt_path = Path(__file__).resolve().parent / "prompts" / "chat_assistant_system.md"

    def run(self, message: str, session_id: str, page_context: dict[str, str]) -> ChatResponse:
        """Answer one user message with evidence-backed read-only tool calls."""

        normalized_message = str(message or "").strip()
        if not normalized_message:
            return ChatResponse(answer="请输入需要查询的问题", session_id=session_id or self._new_session_id())

        current_session_id = session_id.strip() if session_id else self._new_session_id()
        history = list(_sessions.get(current_session_id, []))[-40:]
        tool_calls = self._select_tool_calls(message=normalized_message, page_context=page_context, history=history)
        tool_results: list[dict[str, Any]] = []
        traces: list[ToolCallTrace] = []
        executed: set[str] = set()

        for _round_no in range(self.MAX_TOOL_ROUNDS):
            pending = [item for item in tool_calls if self._tool_key(item) not in executed]
            if not pending:
                break
            for call in pending:
                executed.add(self._tool_key(call))
                result, trace = self._execute_tool(call)
                tool_results.append(result)
                traces.append(trace)
            followups = self._followup_tool_calls(message=normalized_message, page_context=page_context, tool_results=tool_results)
            tool_calls = [item for item in followups if self._tool_key(item) not in executed]

        evidence_refs = self._collect_evidence_refs(tool_results)
        suggested_actions = self._suggest_actions(normalized_message, page_context, tool_results)
        response = self._build_final_response(
            message=normalized_message,
            page_context=page_context,
            tool_results=tool_results,
            traces=traces,
            evidence_refs=evidence_refs,
            suggested_actions=suggested_actions,
            session_id=current_session_id,
        )
        _sessions[current_session_id] = [*history, {"role": "user", "content": normalized_message}, {"role": "assistant", "content": response.answer}][-40:]
        return response

    def _select_tool_calls(self, *, message: str, page_context: dict[str, str], history: list[dict[str, str]]) -> list[dict[str, Any]]:
        llm_calls = self._select_tool_calls_with_model(message=message, page_context=page_context, history=history)
        if llm_calls:
            return llm_calls[: self.MAX_TOOL_ROUNDS]
        return self._select_tool_calls_by_rule(message=message, page_context=page_context)

    def _select_tool_calls_with_model(
        self,
        *,
        message: str,
        page_context: dict[str, str],
        history: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        if self.chat_client is None:
            return []
        prompt = {
            "task": "select_readonly_tools",
            "message": message,
            "page_context": page_context,
            "recent_history": history[-6:],
            "available_tools": [
                "get_overview",
                "get_task_detail",
                "explain_failure",
                "get_doctor_report",
                "get_task_report",
                "get_artifact_content",
                "search_docs_rag",
            ],
            "output_schema": {"tool_calls": [{"name": "tool_name", "arguments": {}}]},
        }
        try:
            result = self.chat_client.chat_json(
                model=self._model_name(),
                system_prompt=self._system_prompt(),
                user_prompt=json.dumps(prompt, ensure_ascii=False, sort_keys=True),
                temperature=0.0,
            )
        except (ModelClientError, OSError, ValueError, TypeError):
            return []
        raw_calls = result.payload.get("tool_calls")
        if not isinstance(raw_calls, list):
            return []
        calls: list[dict[str, Any]] = []
        for item in raw_calls:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            arguments = item.get("arguments") if isinstance(item.get("arguments"), dict) else {}
            if name in self._available_tool_names():
                calls.append({"name": name, "arguments": arguments})
        return calls

    def _select_tool_calls_by_rule(self, *, message: str, page_context: dict[str, str]) -> list[dict[str, Any]]:
        lowered = message.lower()
        task_id = self._extract_task_id(message, page_context)
        calls: list[dict[str, Any]] = []
        if any(keyword in message for keyword in ["环境", "诊断", "依赖", "大模型状态"]):
            calls.append({"name": "get_doctor_report", "arguments": {}})
        if task_id:
            calls.append({"name": "get_task_detail", "arguments": {"task_id": task_id}})
            if "报告" in message:
                calls.append({"name": "get_task_report", "arguments": {"task_id": task_id}})
        if any(keyword in message for keyword in ["文档", "怎么", "如何", "说明", "使用"]):
            calls.append({"name": "search_docs_rag", "arguments": {"query": message}})
        if not calls or any(keyword in message for keyword in ["系统", "总览", "能做什么", "状态"]):
            calls.insert(0, {"name": "get_overview", "arguments": {}})
        if "artifact_path" in page_context or "path" in page_context:
            artifact_path = page_context.get("artifact_path") or page_context.get("path") or ""
            if any(keyword in message for keyword in ["读取", "打开", "内容", "文件"]):
                calls.append({"name": "get_artifact_content", "arguments": {"path": artifact_path}})
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for call in calls:
            key = self._tool_key(call)
            if key not in seen:
                seen.add(key)
                deduped.append(call)
        return deduped[: self.MAX_TOOL_ROUNDS]

    def _execute_tool(self, call: dict[str, Any]) -> tuple[dict[str, Any], ToolCallTrace]:
        name = str(call.get("name") or "")
        arguments = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
        try:
            match name:
                case "get_overview":
                    payload = chat_tools.get_overview(self.context)
                case "get_task_detail":
                    payload = chat_tools.get_task_detail(str(arguments.get("task_id") or ""), self.context)
                case "explain_failure":
                    failure_type = str(arguments.get("failure_type") or "")
                    summary = str(arguments.get("summary") or "")
                    if not failure_type:
                        failure_type, summary = self._latest_failure_from_results([])
                    payload = chat_tools.explain_failure(failure_type, summary, self.context)
                case "get_doctor_report":
                    payload = chat_tools.get_doctor_report(self.context)
                case "get_task_report":
                    payload = chat_tools.get_task_report(str(arguments.get("task_id") or ""), self.context)
                case "get_artifact_content":
                    payload = chat_tools.get_artifact_content(str(arguments.get("path") or ""), self.context)
                case "search_docs_rag":
                    payload = chat_tools.search_docs_rag(str(arguments.get("query") or ""), self.context)
                case _:
                    return {"tool": name, "status": "skipped", "error": "工具未注册"}, ToolCallTrace(name=name, status="skipped", summary="工具未注册")
            return {"tool": name, "status": "success", "payload": payload}, ToolCallTrace(name=name, status="success", summary=self._tool_summary(name, payload))
        except Exception as exc:
            return {"tool": name, "status": "error", "error": str(exc)}, ToolCallTrace(name=name, status="error", summary=str(exc)[:120])

    def _followup_tool_calls(
        self,
        *,
        message: str,
        page_context: dict[str, str],
        tool_results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not any(keyword in message for keyword in ["失败", "原因", "为什么", "归因"]):
            return []
        failure_type, summary = self._latest_failure_from_results(tool_results)
        if not failure_type:
            return []
        return [{"name": "explain_failure", "arguments": {"failure_type": failure_type, "summary": summary}}]

    def _latest_failure_from_results(self, tool_results: list[dict[str, Any]]) -> tuple[str, str]:
        for result in reversed(tool_results):
            if result.get("tool") != "get_task_detail" or result.get("status") != "success":
                continue
            payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}
            attempts = payload.get("latest_attempts") if isinstance(payload, dict) else []
            if not isinstance(attempts, list):
                continue
            for attempt in attempts:
                if isinstance(attempt, dict) and attempt.get("failure_type"):
                    return str(attempt.get("failure_type")), f"attempt {attempt.get('attempt_no')} status {attempt.get('status')}"
        return "", ""

    def _build_final_response(
        self,
        *,
        message: str,
        page_context: dict[str, str],
        tool_results: list[dict[str, Any]],
        traces: list[ToolCallTrace],
        evidence_refs: list[str],
        suggested_actions: list[SuggestedAction],
        session_id: str,
    ) -> ChatResponse:
        llm_response = self._final_response_with_model(
            message=message,
            page_context=page_context,
            tool_results=tool_results,
            evidence_refs=evidence_refs,
            suggested_actions=suggested_actions,
            session_id=session_id,
        )
        if llm_response is None:
            llm_response = self._fallback_response(
                tool_results=tool_results,
                traces=traces,
                evidence_refs=evidence_refs,
                suggested_actions=suggested_actions,
                session_id=session_id,
            )
        return llm_response.model_copy(
            update={
                "tool_calls": traces,
                "evidence_refs": evidence_refs or llm_response.evidence_refs,
                "suggested_actions": suggested_actions or llm_response.suggested_actions,
                "requires_confirmation": bool(suggested_actions) or llm_response.requires_confirmation,
                "session_id": session_id,
            }
        )

    def _final_response_with_model(
        self,
        *,
        message: str,
        page_context: dict[str, str],
        tool_results: list[dict[str, Any]],
        evidence_refs: list[str],
        suggested_actions: list[SuggestedAction],
        session_id: str,
    ) -> ChatResponse | None:
        if self.chat_client is None:
            return None
        prompt = {
            "task": "answer_with_chat_response_schema",
            "message": message,
            "page_context": page_context,
            "tool_results_summary": self._clip_payload(tool_results),
            "evidence_refs": evidence_refs,
            "suggested_actions": [item.model_dump(mode="json") for item in suggested_actions],
            "session_id": session_id,
        }
        try:
            result = self.chat_client.chat_json(
                model=self._model_name(),
                system_prompt=self._system_prompt(),
                user_prompt=json.dumps(prompt, ensure_ascii=False, sort_keys=True),
                temperature=0.1,
            )
            return ChatResponse.model_validate(result.payload)
        except (ModelClientError, ValidationError, OSError, ValueError, TypeError):
            return None

    def _fallback_response(
        self,
        *,
        tool_results: list[dict[str, Any]],
        traces: list[ToolCallTrace],
        evidence_refs: list[str],
        suggested_actions: list[SuggestedAction],
        session_id: str,
    ) -> ChatResponse:
        answer_parts: list[str] = []
        for result in tool_results:
            if result.get("status") != "success":
                continue
            name = str(result.get("tool") or "")
            payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}
            if name == "get_overview":
                metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
                answer_parts.append(
                    f"系统当前记录 {metrics.get('total_tasks', 0)} 个任务，运行中 {metrics.get('running_tasks', 0)} 个，成功率 {metrics.get('success_rate', 0)}%"
                )
            elif name == "get_doctor_report":
                summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
                answer_parts.append(f"环境诊断包含 {summary.get('error', 0)} 个错误，{summary.get('warn', 0)} 个警告")
            elif name == "get_task_detail":
                task = payload.get("task") if isinstance(payload.get("task"), dict) else {}
                answer_parts.append(f"任务 {task.get('task_id')} 当前状态为 {task.get('status')}，尝试轮次 {task.get('current_attempt')}")
            elif name == "explain_failure":
                answer_parts.append(f"失败解释：{payload.get('explanation') or payload.get('failure_type') or '未形成解释'}")
            elif name == "get_task_report":
                answer_parts.append(f"已读取任务报告：{payload.get('report_path')}")
            elif name == "get_artifact_content":
                answer_parts.append(f"已读取产物片段：{payload.get('path')}")
            elif name == "search_docs_rag":
                results = payload.get("results") if isinstance(payload.get("results"), list) else []
                answer_parts.append(f"已检索到 {len(results)} 条相关文档片段")
        if not answer_parts:
            failed = next((trace.summary for trace in traces if trace.status == "error"), "")
            answer_parts.append(f"暂时没有取得可用证据{f'，最近错误：{failed}' if failed else ''}")
        return ChatResponse(
            answer="\n".join(answer_parts),
            evidence_refs=evidence_refs,
            tool_calls=traces,
            suggested_actions=suggested_actions,
            risk="medium" if any(item.status == "error" for item in traces) else "low",
            requires_confirmation=bool(suggested_actions),
            session_id=session_id,
        )

    def _suggest_actions(
        self,
        message: str,
        page_context: dict[str, str],
        tool_results: list[dict[str, Any]],
    ) -> list[SuggestedAction]:
        actions: list[SuggestedAction] = []
        task_id = self._extract_task_id(message, page_context)
        if task_id and any(keyword in message for keyword in ["自动", "运行", "继续", "处理"]):
            actions.append(chat_tools.suggest_start_auto_run(task_id))
        if any(keyword in message for keyword in ["修复环境", "一键修复", "环境修复"]):
            actions.append(chat_tools.suggest_run_doctor_repair())
        cve_id = self._extract_cve_id(message)
        if cve_id and any(keyword in message for keyword in ["创建", "新建", "跑", "处理"]):
            actions.append(chat_tools.suggest_create_task(cve_id, page_context.get("target_kernel", "")))
        return actions

    def _collect_evidence_refs(self, tool_results: list[dict[str, Any]]) -> list[str]:
        refs: list[str] = []
        for result in tool_results:
            payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}
            evidence = payload.get("evidence_refs") if isinstance(payload, dict) else []
            if isinstance(evidence, list):
                refs.extend(str(item) for item in evidence if item)
            for key in ["report_path", "path"]:
                value = payload.get(key) if isinstance(payload, dict) else None
                if value:
                    refs.append(str(value))
        deduped: list[str] = []
        for ref in refs:
            if ref not in deduped:
                deduped.append(ref)
        return deduped

    def _tool_summary(self, name: str, payload: dict[str, Any]) -> str:
        if name == "get_overview":
            metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
            return f"任务 {metrics.get('total_tasks', 0)} 个"
        if name == "get_task_detail":
            task = payload.get("task") if isinstance(payload.get("task"), dict) else {}
            return f"{task.get('task_id')} {task.get('status')}"
        if name == "explain_failure":
            return str(payload.get("explanation") or payload.get("failure_type") or "已解释")
        if name == "get_doctor_report":
            summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
            return f"错误 {summary.get('error', 0)} 个"
        if name == "search_docs_rag":
            results = payload.get("results") if isinstance(payload.get("results"), list) else []
            return f"命中 {len(results)} 条"
        return "已读取"

    def _system_prompt(self) -> str:
        if self.system_prompt_path.exists():
            return self.system_prompt_path.read_text(encoding="utf-8")
        return "你是 PatchWeaver Assistant，只读回答并输出 ChatResponse JSON"

    def _model_name(self) -> str:
        if self.models_config is None:
            return "unknown"
        return self.models_config.helper_models.get("log_summary") or self.models_config.default_model

    def _build_chat_client(self) -> OpenAICompatibleChatClient | None:
        if self.models_config is None or self.models_config.endpoint_mode != "openai_compatible":
            return None
        api_key = self.models_config.resolve_api_key()
        if not api_key:
            return None
        return OpenAICompatibleChatClient(base_url=self.models_config.base_url, api_key=api_key, timeout_sec=20)

    def _extract_task_id(self, message: str, page_context: dict[str, str]) -> str:
        context_task = str(page_context.get("task_id") or "").strip()
        if context_task:
            return context_task
        match = re.search(r"TASK[-_A-Za-z0-9]+", message)
        return match.group(0) if match else ""

    def _extract_cve_id(self, message: str) -> str:
        match = re.search(r"CVE-\d{4}-\d{4,7}", message, flags=re.IGNORECASE)
        return match.group(0).upper() if match else ""

    def _tool_key(self, call: dict[str, Any]) -> str:
        return json.dumps({"name": call.get("name"), "arguments": call.get("arguments") or {}}, ensure_ascii=False, sort_keys=True)

    def _clip_payload(self, payload: Any, *, limit: int = 6000) -> Any:
        text = json.dumps(payload, ensure_ascii=False, default=str)
        if len(text) <= limit:
            return payload
        return {"truncated_summary": text[:limit]}

    @staticmethod
    def _available_tool_names() -> set[str]:
        return {
            "get_overview",
            "get_task_detail",
            "explain_failure",
            "get_doctor_report",
            "get_task_report",
            "get_artifact_content",
            "search_docs_rag",
        }

    @staticmethod
    def _new_session_id() -> str:
        return f"chat-{uuid4().hex[:12]}"
