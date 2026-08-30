"""EmbeddingService 的 LangChain 实现：委托给 langchain-openai 的 OpenAIEmbeddings。

与 OpenAICompatibleEmbeddingService 保持相同的外部行为：
- dimension 仍以配置为准（建 Qdrant collection 时用）
- 关闭 tiktoken 上下文切分，超长文本直接交给服务端（与 native 直传一致）

通过 ZHIYUAN_EMBEDDING_BACKEND=langchain 启用。
"""

from __future__ import annotations

from collections.abc import Sequence

import httpx
from langchain_openai import OpenAIEmbeddings

from app.llm.base import _strip_sdk_headers


class LangChainEmbeddingService:
    """LangChain OpenAIEmbeddings 适配器，满足 EmbeddingService 协议。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        dim: int = 1024,
        timeout: float = 60.0,
    ):
        self._dim = dim
        # OpenAIEmbeddings 底层走 openai SDK，同样需要剥离 x-stainless-* 指纹头
        self._http = httpx.AsyncClient(
            trust_env=False,
            timeout=timeout,
            event_hooks={"request": [_strip_sdk_headers]},
        )
        self._embeddings = OpenAIEmbeddings(
            model=model,
            api_key=api_key,
            base_url=base_url,
            check_embedding_ctx_length=False,
            http_async_client=self._http,
        )

    @property
    def dimension(self) -> int:
        return self._dim

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return await self._embeddings.aembed_documents(list(texts))

    async def embed_one(self, text: str) -> list[float]:
        return await self._embeddings.aembed_query(text)

    async def close(self) -> None:
        """只关自建的 httpx 客户端；OpenAIEmbeddings 没有公开的关闭接口。"""
        await self._http.aclose()
