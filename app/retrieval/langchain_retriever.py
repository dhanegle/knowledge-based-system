"""把 Zhiyuan 的向量检索包装成 LangChain BaseRetriever。

供 LangChain 生态直接复用现有 Qdrant 检索（多查询改写、上下文压缩等
组合检索器，以及 LCEL 管线），Qdrant payload 结构零迁移。
只支持异步调用（底层 embed 与 Qdrant 查询都是 async）。
"""

from __future__ import annotations

from typing import Any

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever


class ZhiyuanRetriever(BaseRetriever):
    """VectorSearcher 的 LangChain Retriever 适配。"""

    searcher: Any | None = None
    doc_ids: list[str] | None = None

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> list[Document]:
        raise NotImplementedError(
            "ZhiyuanRetriever 只支持异步调用：请使用 ainvoke() 或在异步 LCEL 链中使用"
        )

    async def _aget_relevant_documents(
        self,
        query: str,
        *,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> list[Document]:
        searcher = self.searcher
        if searcher is None:
            from app.retrieval.vector_search import VectorSearcher

            searcher = VectorSearcher()
            self.searcher = searcher

        chunks = await searcher.search(query, doc_ids=self.doc_ids)
        return [
            Document(
                page_content=c.text,
                metadata={
                    "doc_id": c.doc_id,
                    "filename": c.filename,
                    "page": c.page,
                    "chunk_index": c.chunk_index,
                    "score": c.score,
                },
            )
            for c in chunks
        ]
