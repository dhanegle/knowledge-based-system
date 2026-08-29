"""Qdrant 向量库客户端封装。

负责：创建集合、upsert 向量、按向量搜索、按 doc_id 删除。
向量维度和距离度量从 settings 读取。
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """向量搜索结果。"""
    text: str
    score: float
    doc_id: str
    filename: str
    page: int
    chunk_index: int


class QdrantStore:
    """Qdrant 向量库封装。"""

    def __init__(self, url: str, collection: str, vector_dim: int):
        self._client = AsyncQdrantClient(url=url)
        self._collection = collection
        self._vector_dim = vector_dim

    async def ensure_collection(self) -> None:
        """确保集合存在，不存在则创建。"""
        collections = await self._client.get_collections()
        names = [c.name for c in collections.collections]
        if self._collection not in names:
            await self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(
                    size=self._vector_dim,
                    distance=Distance.COSINE,
                ),
            )
            logger.info("创建 Qdrant 集合: %s (dim=%d)", self._collection, self._vector_dim)

    async def upsert_chunks(
        self,
        doc_id: str,
        filename: str,
        chunks: Sequence[tuple[str, list[float], int]],
    ) -> int:
        """批量写入 chunks 的向量。

        Args:
            doc_id: 文档 ID
            filename: 文件名
            chunks: [(text, vector, page), ...]
        Returns:
            写入的点数
        """
        points = []
        for idx, (text, vector, page) in enumerate(chunks):
            points.append(PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={
                    "text": text,
                    "doc_id": doc_id,
                    "filename": filename,
                    "page": page,
                    "chunk_index": idx,
                },
            ))

        if points:
            await self._client.upsert(collection_name=self._collection, points=points)
        return len(points)

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 20,
        doc_ids: list[str] | None = None,
    ) -> list[SearchResult]:
        """向量搜索，返回 top_k 结果。可选按 doc_id 过滤。"""
        query_filter = None
        if doc_ids:
            query_filter = Filter(must=[
                FieldCondition(key="doc_id", match=MatchValue(any=doc_ids))
            ])

        results = await self._client.query_points(
            collection_name=self._collection,
            query=query_vector,
            limit=top_k,
            query_filter=query_filter,
        )

        return [
            SearchResult(
                text=hit.payload.get("text", ""),
                score=hit.score,
                doc_id=hit.payload.get("doc_id", ""),
                filename=hit.payload.get("filename", ""),
                page=hit.payload.get("page", 0),
                chunk_index=hit.payload.get("chunk_index", 0),
            )
            for hit in results.points
        ]

    async def delete_by_doc_id(self, doc_id: str) -> None:
        """删除某文档的所有 chunks（按 doc_id 过滤）。"""
        await self._client.delete(
            collection_name=self._collection,
            points_selector=Filter(must=[
                FieldCondition(key="doc_id", match=MatchValue(value=doc_id))
            ]),
        )

    async def close(self) -> None:
        await self._client.close()


_store: QdrantStore | None = None


def get_qdrant_store() -> QdrantStore:
    global _store
    from app.config import settings
    if _store is None:
        _store = QdrantStore(
            url=settings.qdrant_url,
            collection=settings.qdrant_collection,
            vector_dim=settings.embedding_dim,
        )
    return _store
