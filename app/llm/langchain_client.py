"""LLMClient 的 LangChain 实现：委托给 langchain-openai 的 ChatOpenAI。

与 OpenAICompatibleLLMClient 保持相同的外部行为：
- 消息拼法一致（system 提示 + "参考信息：…\n\n问题：…"）
- 同样剥离 openai SDK 的 x-stainless-* 指纹头（部分网关会因此 403）

通过 ZHIYUAN_LLM_BACKEND=langchain 启用。
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.llm.base import _strip_sdk_headers


class LangChainLLMClient:
    """LangChain ChatOpenAI 适配器，满足 LLMClient 协议。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        max_tokens: int = 4096,
        timeout: float = 120.0,
    ):
        # ChatOpenAI 底层同样走 openai SDK，必须沿用同一份请求头清洗钩子
        self._http = httpx.AsyncClient(
            trust_env=False,
            timeout=timeout,
            event_hooks={"request": [_strip_sdk_headers]},
        )
        self._llm = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            max_tokens=max_tokens,
            streaming=True,
            http_async_client=self._http,
        )

    @property
    def chat_model(self) -> ChatOpenAI:
        """暴露底层 ChatOpenAI，供 RAGService 在 LangChain 后端时组装 LCEL 链。"""
        return self._llm

    async def stream(
        self,
        question: str,
        *,
        system_prompt: str = "",
        context: str = "",
    ) -> AsyncIterator[str]:
        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        if context:
            user_content = f"参考信息：\n{context}\n\n问题：{question}"
        else:
            user_content = question
        messages.append(HumanMessage(content=user_content))

        async for chunk in self._llm.astream(messages):
            for piece in _text_pieces(chunk.content):
                if piece:
                    yield piece

    async def aclose(self) -> None:
        """只关自建的 httpx 客户端；ChatOpenAI 没有公开的关闭接口。"""
        await self._http.aclose()


def _text_pieces(content: str | list) -> list[str]:
    """把 AIMessageChunk.content 归一化为文本片段列表。

    文本模型返回 str；部分模型返回 content-block 列表，取其中 text 字段。
    """
    if isinstance(content, str):
        return [content]
    return [block.get("text", "") for block in content if isinstance(block, dict)]
