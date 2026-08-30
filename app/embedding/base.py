"""Embedding 服务接口。

和 LLM 一样的抽象模式：定义协议 + Stub 占位实现。
等用户提供 Qwen embedding 的 URL 和 key 后，接入真实实现。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

import httpx


class EmbeddingService(Protocol):
    """Embedding 服务接口。"""

    @property
    def dimension(self) -> int:
        """返回向量维度。"""
        ...

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """批量嵌入文本，返回向量列表。"""
        ...

    async def embed_one(self, text: str) -> list[float]:
        """嵌入单段文本。"""
        ...

    async def close(self) -> None:
        """释放资源。"""
        ...


class StubEmbeddingService:
    """占位实现：生成确定性伪向量，不调用任何 API。

    用于跑通摄入管线和 Qdrant 写入链路。等 embedding key 到了后替换。
    """

    def __init__(self, dim: int = 1024):
        self._dim = dim

    @property
    def dimension(self) -> int:
        return self._dim

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        import hashlib
        results = []
        for text in texts:
            h = hashlib.sha256(text.encode("utf-8")).digest()
            vec = [(h[i % len(h)] / 255.0 - 0.5) * 2 for i in range(self._dim)]
            results.append(vec)
        return results

    async def embed_one(self, text: str) -> list[float]:
        return (await self.embed([text]))[0]

    async def close(self) -> None:
        pass


class OpenAICompatibleEmbeddingService:
    """OpenAI 兼容接口的 Embedding 服务（适用于 Qwen / 其他兼容服务）。

    等用户提供 URL 和 key 后启用。
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        dim: int = 1024,
        timeout: float = 60.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._dim = dim
        self._client = httpx.AsyncClient(
            trust_env=False,
            timeout=timeout,
        )

    @property
    def dimension(self) -> int:
        return self._dim

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        resp = await self._client.post(
            f"{self._base_url}/embeddings",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"model": self._model, "input": list(texts)},
        )
        resp.raise_for_status()
        data = resp.json()
        return [item["embedding"] for item in data["data"]]

    async def embed_one(self, text: str) -> list[float]:
        return (await self.embed([text]))[0]

    async def close(self) -> None:
        await self._client.aclose()


_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """根据配置返回合适的 embedding 服务。

    - ZHIYUAN_EMBEDDING_BACKEND=langchain 且配置齐全 → LangChainEmbeddingService
    - 配置齐全 → OpenAICompatibleEmbeddingService
    - 否则 → StubEmbeddingService（占位）
    """
    global _embedding_service
    from app.config import settings

    if _embedding_service is not None:
        return _embedding_service

    if settings.embedding_configured:
        if settings.embedding_backend == "langchain":
            # 延迟导入：native 模式不必导入 langchain-openai
            from app.embedding.langchain_service import LangChainEmbeddingService

            _embedding_service = LangChainEmbeddingService(
                base_url=settings.embedding_base_url,
                api_key=settings.embedding_api_key,
                model=settings.embedding_model,
                dim=settings.embedding_dim,
            )
        else:
            _embedding_service = OpenAICompatibleEmbeddingService(
                base_url=settings.embedding_base_url,
                api_key=settings.embedding_api_key,
                model=settings.embedding_model,
                dim=settings.embedding_dim,
            )
    else:
        _embedding_service = StubEmbeddingService(dim=settings.embedding_dim)

    return _embedding_service
