"""RAG 编排：检索 → 重排 → 拼 prompt → LLM 流式生成。

把 VectorSearcher、RerankerService、LLMClient 串成一条查询管线。

LLM 后端为 LangChain（ZHIYUAN_LLM_BACKEND=langchain）时，生成段走 LCEL 链
（chat_model | StrOutputParser），配置了 Langfuse 时整链自动上报 trace；
其余后端走原生 stream 路径。两条路径的返回签名与行为一致。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.llm.base import LLMClient
from app.observability.langfuse import get_langchain_callback_handler, trace_span
from app.rag.prompt_builder import SYSTEM_PROMPT, build_context, build_user_message
from app.retrieval.reranker import RerankedChunk, RerankerService, get_reranker
from app.retrieval.vector_search import VectorSearcher

if TYPE_CHECKING:
    from langchain_core.chat_models import BaseChatModel

logger = structlog.get_logger("app.rag")


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
        chat_model: BaseChatModel | None = None,
    ):
        self._llm = llm_client
        self._searcher = searcher or VectorSearcher()
        self._reranker = reranker or get_reranker()
        self._chat_model = chat_model

    @trace_span("rag_ask")
    async def ask(self, question: str, doc_ids: list[str] | None = None) -> tuple[AsyncIterator[str], list[dict]]:
        """执行 RAG 查询，返回 (流式回答迭代器, 引用来源列表)。"""
        # 1. 向量检索
        chunks = await self._searcher.search(question, doc_ids=doc_ids)

        if self._chat_model is not None:
            return await self._ask_lcel(question, chunks)
        return await self._ask_native(question, chunks)

    async def _ask_native(
        self,
        question: str,
        chunks: list,
    ) -> tuple[AsyncIterator[str], list[dict]]:
        if not chunks:
            logger.info("rag_no_results", question_preview=question[:50])

            @trace_span("rag_generate")
            async def no_context_stream():
                async for token in self._llm.stream(question, system_prompt=SYSTEM_PROMPT):
                    yield token

            return no_context_stream(), []

        reranked = await self._reranker.rerank(question, chunks, top_k=5)
        context = build_context(reranked)
        user_message = build_user_message(question, context)
        sources = self._collect_sources(reranked)
        logger.info("rag_pipeline", retrieved=len(chunks), reranked=len(reranked))
        stream = self._llm.stream(user_message, system_prompt=SYSTEM_PROMPT)
        return stream, sources

    async def _ask_lcel(
        self,
        question: str,
        chunks: list,
    ) -> tuple[AsyncIterator[str], list[dict]]:
        """LangChain 后端路径：检索/重排预取（sources 需先于 token 返回），
        生成段组成 LCEL 链，Langfuse handler 挂在链 config 上。"""
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_core.output_parsers import StrOutputParser

        if chunks:
            reranked = await self._reranker.rerank(question, chunks, top_k=5)
            logger.info("rag_pipeline", retrieved=len(chunks), reranked=len(reranked))
        else:
            logger.info("rag_no_results", question_preview=question[:50])
            reranked = []

        sources = self._collect_sources(reranked)
        context = build_context(reranked)
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=build_user_message(question, context)),
        ]

        chain = self._chat_model | StrOutputParser()
        handler = get_langchain_callback_handler()
        config = {"callbacks": [handler]} if handler else None

        async def _stream():
            if config is not None:
                async for token in chain.astream(messages, config=config):
                    yield token
            else:
                async for token in chain.astream(messages):
                    yield token

        return _stream(), sources

    @staticmethod
    def _collect_sources(reranked: list[RerankedChunk]) -> list[dict]:
        return [
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
