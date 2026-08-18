import json
import logging

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from app.llm.base import get_llm_client

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/ask")
async def ask(q: str, request: Request):
    """流式问答端点（RAG）。

    通过 SSE（Server-Sent Events）把 LLM 的回答逐块推送给客户端。
    先从知识库检索相关片段，重排后作为上下文交给 LLM 生成带引用的回答。
    """
    # 优先用 app.state 中的共享 RAG 服务；回退到直接 LLM 调用
    rag_service = getattr(request.app.state, "rag_service", None)

    if rag_service is not None:
        stream, sources = await rag_service.ask(q)
    else:
        client = getattr(request.app.state, "llm_client", None) or get_llm_client()
        sources = []

        async def stream():
            async for chunk in client.stream(q):
                yield chunk

    async def event_generator():
        # 先发送来源引用
        if sources:
            yield {
                "event": "sources",
                "data": json.dumps({"sources": sources}, ensure_ascii=False),
            }
        try:
            async for chunk in stream:
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

    return EventSourceResponse(
        event_generator(),
        headers={"X-Accel-Buffering": "no"},
    )
