"""流式问答端点（RAG + Redis 缓存 + 对话持久化）。"""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.cache import get_cached_answer, set_cached_answer
from app.llm.base import get_llm_client
from app.storage.conversation import Conversation, Message
from app.storage.session import get_session

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/ask")
async def ask(
    q: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    doc_ids: str | None = None,
    conversation_id: str | None = None,
):
    """流式问答端点（RAG）。

    通过 SSE 把 LLM 回答逐块推送。流式完成后自动保存消息到对话历史。
    如果 conversation_id 为 None，自动创建新对话。
    """
    doc_id_list = [d.strip() for d in doc_ids.split(",")] if doc_ids else None

    # 1. 查缓存
    cached = await get_cached_answer(q, doc_id_list)
    if cached is not None:
        conv_id = await _ensure_conversation(conversation_id, current_user.id, q)
        await _save_messages(conv_id, q, cached.get("answer", ""), cached.get("sources"))

        async def cached_generator():
            if cached.get("sources"):
                yield {
                    "event": "sources",
                    "data": json.dumps({"sources": cached["sources"]}, ensure_ascii=False),
                }
            yield {
                "event": "token",
                "data": json.dumps({"text": cached["answer"]}, ensure_ascii=False),
            }
            yield {
                "event": "done",
                "data": json.dumps({"ok": True, "cached": True, "conversation_id": conv_id}),
            }

        return EventSourceResponse(
            cached_generator(),
            headers={"X-Accel-Buffering": "no"},
        )

    # 2. 未命中缓存 → 正常 RAG 流程
    rag_service = getattr(request.app.state, "rag_service", None)

    if rag_service is not None:
        stream, sources = await rag_service.ask(q, doc_ids=doc_id_list)
    else:
        client = getattr(request.app.state, "llm_client", None) or get_llm_client()
        sources = []

        async def stream():
            async for chunk in client.stream(q):
                yield chunk

    # 确保对话存在
    conv_id = await _ensure_conversation(conversation_id, current_user.id, q)

    # 收集完整回答用于缓存和持久化
    collected_tokens: list[str] = []

    async def event_generator():
        # 先发送来源引用
        if sources:
            yield {
                "event": "sources",
                "data": json.dumps({"sources": sources}, ensure_ascii=False),
            }
        try:
            async for chunk in stream:
                collected_tokens.append(chunk)
                yield {
                    "event": "token",
                    "data": json.dumps({"text": chunk}, ensure_ascii=False),
                }
        except Exception:
            logger.exception("LLM streaming failed")
            yield {
                "event": "error",
                "data": json.dumps(
                    {"ok": False, "error": "LLM request failed"}, ensure_ascii=False
                ),
            }
        else:
            yield {
                "event": "done",
                "data": json.dumps({"ok": True, "conversation_id": conv_id}),
            }
            # 写缓存 + 持久化消息
            full_answer = "".join(collected_tokens)
            if full_answer:
                await set_cached_answer(
                    q,
                    {"answer": full_answer, "sources": sources},
                    doc_ids=doc_id_list,
                )
                await _save_messages(conv_id, q, full_answer, sources)

    return EventSourceResponse(
        event_generator(),
        headers={"X-Accel-Buffering": "no"},
    )


async def _ensure_conversation(
    conversation_id: str | None,
    user_id: str,
    question: str,
) -> str:
    """确保对话存在，如果 conversation_id 为 None 则自动创建。"""
    if conversation_id:
        return conversation_id

    title = question[:30] + ("..." if len(question) > 30 else "")
    conv = Conversation(
        id=str(uuid.uuid4()),
        user_id=user_id,
        title=title,
    )
    async with get_session() as session:
        session.add(conv)
        await session.commit()
    return conv.id


async def _save_messages(
    conv_id: str,
    question: str,
    answer: str,
    sources: list | None,
) -> None:
    """保存用户问题和 AI 回答到数据库。"""
    sources_json = json.dumps(sources or [], ensure_ascii=False) if sources else None
    async with get_session() as session:
        session.add(Message(
            id=str(uuid.uuid4()),
            conversation_id=conv_id,
            role="user",
            content=question,
            sources=None,
        ))
        session.add(Message(
            id=str(uuid.uuid4()),
            conversation_id=conv_id,
            role="assistant",
            content=answer,
            sources=sources_json,
        ))
        await session.commit()
