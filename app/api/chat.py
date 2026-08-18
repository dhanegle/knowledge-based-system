"""流式问答端点（RAG + Redis 缓存）。"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from app.cache import get_cached_answer, set_cached_answer
from app.llm.base import get_llm_client

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/ask")
async def ask(q: str, request: Request, doc_ids: str | None = None):
    """流式问答端点（RAG）。

    通过 SSE（Server-Sent Events）把 LLM 的回答逐块推送给客户端。
    先从知识库检索相关片段，重排后作为上下文交给 LLM 生成带引用的回答。
    命中缓存时直接返回完整回答，不流式。
    """
    doc_id_list = [d.strip() for d in doc_ids.split(",")] if doc_ids else None

    # 1. 查缓存
    cached = await get_cached_answer(q, doc_id_list)
    if cached is not None:
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
                "data": json.dumps({"ok": True, "cached": True}),
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

    # 收集完整回答用于缓存
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
            yield {"event": "done", "data": json.dumps({"ok": True})}
            # 写缓存（非失败时）
            full_answer = "".join(collected_tokens)
            if full_answer:
                await set_cached_answer(
                    q,
                    {"answer": full_answer, "sources": sources},
                    doc_ids=doc_id_list,
                )

    return EventSourceResponse(
        event_generator(),
        headers={"X-Accel-Buffering": "no"},
    )
