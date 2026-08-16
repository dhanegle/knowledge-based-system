import json
import logging

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from app.llm.base import get_llm_client

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/ask")
async def ask(q: str, request: Request):
    """流式问答端点。

    通过 SSE（Server-Sent Events）把 LLM 的回答逐块推送给客户端。
    当前是 StubLLMClient 占位实现；接入真实 LLM 后自动切换。
    """
    # The lifespan creates the shared client. The fallback keeps direct calls
    # to this handler usable in small tests and local integrations.
    client = getattr(request.app.state, "llm_client", None) or get_llm_client()

    async def event_generator():
        try:
            async for chunk in client.stream(q):
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
        headers={"X-Accel-Buffering": "no"},  # 防止 nginx 缓冲 SSE
    )
