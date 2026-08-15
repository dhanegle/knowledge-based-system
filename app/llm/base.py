from typing import AsyncIterator, Protocol


class LLMClient(Protocol):
    """LLM 客户端接口。

    所有具体实现（Claude / OpenAI 兼容 / Qwen 等）都实现这个协议，
    系统其他部分只依赖此接口，不绑死具体模型。
    """

    async def stream(
        self,
        question: str,
        *,
        system_prompt: str = "",
        context: str = "",
    ) -> AsyncIterator[str]:
        """流式生成回答，逐块 yield 文本片段。"""
        ...


class StubLLMClient:
    """占位实现：不调用任何外部 API，仅用于跑通 SSE 链路。

    等用户提供 LLM 的 URL 和 key 后，替换为真实实现。
    """

    async def stream(
        self,
        question: str,
        *,
        system_prompt: str = "",
        context: str = "",
    ) -> AsyncIterator[str]:
        yield f"[知源·占位回答] 你问了：「{question}」\n\n"
        yield "（当前是 StubLLMClient 占位实现，未接入真实 LLM。"
        yield "请在 .env 中配置 ZHIYUAN_LLM_BASE_URL 和 ZHIYUAN_LLM_API_KEY 后重启。）"


def get_llm_client() -> LLMClient:
    """根据配置返回合适的 LLM 客户端。

    当 llm_api_key 为空时，返回 StubLLMClient。
    有 key 后，在这里切换到真实实现。
    """
    from app.config import settings

    if not settings.llm_api_key:
        return StubLLMClient()

    raise NotImplementedError(
        "真实 LLM 客户端尚未接入。请在 app/llm/client.py 中实现后，在此返回。"
    )
