from collections.abc import AsyncIterator
from typing import Protocol

import httpx
from openai import AsyncOpenAI


async def _strip_sdk_headers(request: httpx.Request) -> None:
    """移除 openai SDK 的 x-stainless-* 请求头。

    某些 API 网关（如 newapi.sorai.me）会拦截这些 SDK 指纹头导致 403。
    """
    for key in list(request.headers.keys()):
        if key.startswith("x-stainless"):
            del request.headers[key]
    request.headers["user-agent"] = "zhiyuan/0.1"


class LLMClient(Protocol):
    """LLM 客户端接口。

    所有具体实现（OpenAI 兼容 / Claude / Qwen 等）都实现这个协议，
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
    """占位实现：不调用任何外部 API，仅用于跑通 SSE 链路。"""

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


class OpenAICompatibleLLMClient:
    """OpenAI 兼容接口的 LLM 客户端。

    适用于任何遵循 OpenAI Chat Completions API 格式的服务
   （OpenAI / DeepSeek / MiniMax / Qwen / 自建网关等）。
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        max_tokens: int = 4096,
        timeout: float = 120.0,
    ):
        self._client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            http_client=httpx.AsyncClient(
                trust_env=False,
                event_hooks={"request": [_strip_sdk_headers]},
            ),
        )
        self._model = model
        self._max_tokens = max_tokens

    async def stream(
        self,
        question: str,
        *,
        system_prompt: str = "",
        context: str = "",
    ) -> AsyncIterator[str]:
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if context:
            user_content = f"参考信息：\n{context}\n\n问题：{question}"
        else:
            user_content = question
        messages.append({"role": "user", "content": user_content})

        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=self._max_tokens,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta


def get_llm_client() -> LLMClient:
    """根据配置返回合适的 LLM 客户端。

    - 有 base_url + api_key + model → OpenAICompatibleLLMClient
    - 否则 → StubLLMClient（占位）
    """
    from app.config import settings

    if settings.llm_base_url and settings.llm_api_key and settings.llm_model:
        return OpenAICompatibleLLMClient(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            max_tokens=settings.llm_max_tokens,
            timeout=settings.llm_timeout,
        )

    return StubLLMClient()
