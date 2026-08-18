"""摄入管线：编排 parse → chunk → embed → store。

把解析器、分块器、embedding 服务、Qdrant、Postgres 串成一条流水线。
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass

from app.embedding.base import get_embedding_service
from app.ingestion.chunker import TextChunker
from app.ingestion.parser import DocumentParser, ParsedDocument
from app.storage.postgres import Document, DocumentStatus
from app.storage.qdrant import get_qdrant_store
from app.storage.session import get_session

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    """摄入结果。"""
    doc_id: str
    filename: str
    chunk_count: int
    status: DocumentStatus
    error: str | None = None


class IngestionPipeline:
    """文档摄入管线。"""

    def __init__(self):
        self._parser = DocumentParser()
        self._chunker = TextChunker()
        self._embedder = get_embedding_service()
        self._qdrant = get_qdrant_store()

    async def ingest_file(self, filepath: str) -> IngestionResult:
        """摄入单个文件：解析 → 分块 → 向量化 → 入库。"""
        import pathlib
        path = pathlib.Path(filepath)
        doc_id = str(uuid.uuid4())
        file_size = path.stat().st_size
        checksum = self._checksum(path)

        # 1. 创建文档记录
        async with get_session() as session:
            doc = Document(
                id=doc_id,
                filename=path.name,
                file_type=path.suffix.lower(),
                file_size=file_size,
                checksum=checksum,
                status=DocumentStatus.parsing,
            )
            session.add(doc)
            await session.commit()

        try:
            # 2. 解析
            parsed: ParsedDocument = self._parser.parse(path)

            # 3. 更新状态 → chunking
            await self._update_status(doc_id, DocumentStatus.chunking)

            # 4. 分块
            chunks = self._chunker.chunk_pages(parsed.pages, filename=parsed.filename)
            if not chunks:
                raise ValueError("文档解析后无有效文本内容")

            # 5. 更新状态 → embedding
            await self._update_status(doc_id, DocumentStatus.embedding)

            # 6. 批量向量化
            texts = [c.text for c in chunks]
            vectors = await self._embedder.embed(texts)

            # 7. 写入 Qdrant
            await self._qdrant.ensure_collection()
            chunks_with_vectors = [
                (c.text, vec, c.page_index + 1)
                for c, vec in zip(chunks, vectors)
            ]
            count = await self._qdrant.upsert_chunks(
                doc_id=doc_id,
                filename=parsed.filename,
                chunks=chunks_with_vectors,
            )

            # 8. 更新文档记录 → indexed
            await self._update_status(
                doc_id, DocumentStatus.indexed, chunk_count=count
            )

            logger.info("摄入完成: %s → %d chunks (doc_id=%s)", parsed.filename, count, doc_id)
            return IngestionResult(
                doc_id=doc_id,
                filename=parsed.filename,
                chunk_count=count,
                status=DocumentStatus.indexed,
            )

        except Exception as e:
            logger.exception("摄入失败: %s", path.name)
            await self._update_status(doc_id, DocumentStatus.failed, error=str(e))
            return IngestionResult(
                doc_id=doc_id,
                filename=path.name,
                chunk_count=0,
                status=DocumentStatus.failed,
                error=str(e),
            )

    async def delete_document(self, doc_id: str) -> bool:
        """删除文档：先删 Qdrant 中的 chunks，再删 Postgres 记录。"""
        from sqlalchemy import select, delete as sa_delete

        # 先删 Qdrant
        await self._qdrant.delete_by_doc_id(doc_id)

        # 再删 Postgres
        async with get_session() as session:
            result = await session.execute(
                sa_delete(Document).where(Document.id == doc_id)
            )
            await session.commit()
            return result.rowcount > 0

    def _checksum(self, path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(8192), b""):
                h.update(block)
        return h.hexdigest()

    async def _update_status(
        self,
        doc_id: str,
        status: DocumentStatus,
        chunk_count: int | None = None,
        error: str | None = None,
    ) -> None:
        from sqlalchemy import update

        values: dict = {"status": status}
        if chunk_count is not None:
            values["chunk_count"] = chunk_count
        if error is not None:
            values["error"] = error

        async with get_session() as session:
            await session.execute(
                update(Document).where(Document.id == doc_id).values(**values)
            )
            await session.commit()


_pipeline: IngestionPipeline | None = None


def get_pipeline() -> IngestionPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = IngestionPipeline()
    return _pipeline
