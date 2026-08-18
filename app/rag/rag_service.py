"""RAG 编排：检索 → 重排 → 拼 prompt → LLM 流式生成。

把 VectorSearcher、RerankerService、LLMClient 串成一条查询管线。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.llm.base import LLMClient, get_llm_client
from app.rag.prompt_builder import SYSTEM_PROMPT, build_context, build_user_message
from app.retrieval.reranker import RerankedChunk, get_reranker
from app.retrieval.vector_search import VectorSearcher

logger = logging.getLogger(__name__)


@dataclass
class RAGResult:
    """RAG 查询结果，包含引用来源。"""
    sources: list[dict]


class RAGService:
    """RAG 查询服务：问题 → 检索 → 重排 → 生成。"""

    def __init__(
        self,
        llm_client: LLMClient,
        searcher: VectorSearcher | None = None,
        reranker: RerankerService | None = None,
    ):
        self._llm = llm_client
        self._searcher = searcher or VectorSearcher()
        self._reranker = reranker or get_reranker()

    async def ask(self, question: str, doc_ids: list[str] | None = None) -> tuple[AsyncIterator[str], list[dict]]:
        """执行 RAG 查询，返回 (流式回答迭代器, 引用来源列表)。"""
        # 1. 向量检索
        chunks = await self._searcher.search(question, doc_ids=doc_ids)

        if not chunks:
            logger.info("RAG: 无检索结果，直接回答")

            async def no_context_stream():
                async for token in self._llm.stream(question, system_prompt=SYSTEM_PROMPT):
                    yield token

            return no_context_stream(), []

        # 2. 重排
        reranked = await self._reranker.rerank(question, chunks, top_k=5)

        # 3. 构建 prompt
        context = build_context(reranked)
        user_message = build_user_message(question, context)

        # 4. 收集引用来源
        sources = [
            {
                "filename": c.filename,
                "page": c.page,
                "score": round(c.score, 4),
                "doc_id": c.doc_id,
                "chunk_index": c.chunk_index,
                "text_preview": c.text[:100],
            }
            for c in reranked
        ]

        logger.info("RAG: %d 检索 → %d 重排 → 生成", len(chunks), len(reranked))

        # 5. 流式生成
        stream = self._llm.stream(user_message, system_prompt=SYSTEM_PROMPT)
        return stream, sources
