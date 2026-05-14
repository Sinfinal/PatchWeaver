"""Read-only Web Chat Assistant route."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from patchweaver.agent.chat_agent import ChatAgent
from patchweaver.api.deps import ApiContext, get_api_context
from patchweaver.api.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest, context: ApiContext = Depends(get_api_context)) -> ChatResponse:
    """Answer one read-only operations question."""

    try:
        return ChatAgent(context).run(request.message, request.session_id, request.context)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
