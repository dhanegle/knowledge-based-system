import json

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.llm.base import get_llm_client

router = APIRouter()


@router.get("/ask")
async def ask(q: str):
    """流式问答端点。

    通过 SSE（Server-Sent Events）把 LLM 的回答逐块推送给客户端。
    当前是 StubLLMClient 占位实现；接入真实 LLM 后自动切换。
    """
    client = get_llm_client()

    async def event_generator():
        async for chunk in client.stream(q):
            yield {"event": "token", "data": json.dumps({"text": chunk}, ensure_ascii=False)}
        yield {"event": "done", "data": json.dumps({"ok": True})}

    return EventSourceResponse(
        event_generator(),
        headers={"X-Accel-Buffering": "no"},  # 防止 nginx 缓冲 SSE
    )
