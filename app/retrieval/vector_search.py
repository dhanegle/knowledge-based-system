"""向量检索：把用户问题 embedding 后在 Qdrant 搜索 top-K。"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.embedding.base import get_embedding_service
from app.storage.qdrant import SearchResult, get_qdrant_store

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    """检索到的一个文本块，带来源元数据。"""
    text: str
    score: float
    doc_id: str
    filename: str
    page: int
    chunk_index: int


class VectorSearcher:
    """向量检索器：问题 → embedding → Qdrant 搜索 → RetrievedChunk 列表。"""

    def __init__(self, top_k: int = 20):
        self._top_k = top_k
        self._embedder = get_embedding_service()
        self._qdrant = get_qdrant_store()

    async def search(self, query: str, doc_ids: list[str] | None = None) -> list[RetrievedChunk]:
        """检索与 query 最相关的文本块。"""
        query_vector = await self._embedder.embed_one(query)
        results: list[SearchResult] = await self._qdrant.search(
            query_vector=query_vector,
            top_k=self._top_k,
            doc_ids=doc_ids,
        )
        logger.info("向量检索: query=%r → %d 结果", query[:50], len(results))
        return [
            RetrievedChunk(
                text=r.text,
                score=r.score,
                doc_id=r.doc_id,
                filename=r.filename,
                page=r.page,
                chunk_index=r.chunk_index,
            )
            for r in results
        ]
