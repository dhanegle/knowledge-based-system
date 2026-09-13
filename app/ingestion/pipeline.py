"""摄入管线：编排 parse → chunk → embed → store。

把解析器、分块器、embedding 服务、Qdrant、Postgres 串成一条流水线。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from dataclasses import dataclass

from app.config import settings
from app.embedding.base import get_embedding_service
from app.errors import DocumentParseError, EmbeddingError, QdrantError
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
        self._chunker = TextChunker(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
        self._embedder = get_embedding_service()
        self._qdrant = get_qdrant_store()

    async def register_pending(
        self, filepath: str, *, filename: str | None = None
    ) -> IngestionResult:
        """创建 pending 文档记录，供后台任务开始实际摄入。"""
        import pathlib

        path = pathlib.Path(filepath)
        display_filename = filename or path.name
        file_size = path.stat().st_size
        checksum = await asyncio.to_thread(self._checksum, path)
        existing = await self._find_by_checksum(checksum)
        if existing is not None:
            existing_status = DocumentStatus(existing.status)
            if existing_status == DocumentStatus.failed:
                # 失败文档必须允许重试。否则 checksum 去重会把它永久锁死：
                # 重新上传走 register_pending、点「重新摄入」走 reingest，
                # 两条路都因「已存在同 checksum 文档」而早退，用户无从恢复。
                # 复用原 doc_id，状态回到 pending，由调用方重新摄入。
                await self._update_status(
                    existing.id, DocumentStatus.pending, clear_error=True
                )
                logger.info(
                    "重试先前失败的文档: %s (doc_id=%s)", existing.filename, existing.id
                )
                return IngestionResult(
                    doc_id=existing.id,
                    filename=existing.filename,
                    chunk_count=0,
                    status=DocumentStatus.pending,
                )
            return IngestionResult(
                doc_id=existing.id,
                filename=existing.filename,
                chunk_count=existing.chunk_count,
                status=existing_status,
                error=existing.error,
            )

        doc_id = str(uuid.uuid4())
        async with get_session() as session:
            session.add(
                Document(
                    id=doc_id,
                    filename=display_filename,
                    file_type=pathlib.Path(display_filename).suffix.lower(),
                    file_size=file_size,
                    checksum=checksum,
                    status=DocumentStatus.pending,
                )
            )
            await session.commit()
        return IngestionResult(
            doc_id=doc_id,
            filename=display_filename,
            chunk_count=0,
            status=DocumentStatus.pending,
        )

    async def ingest_file(
        self,
        filepath: str,
        *,
        doc_id: str | None = None,
        filename: str | None = None,
        pre_registered: bool = False,
    ) -> IngestionResult:
        """摄入单个文件：解析 → 分块 → 向量化 → 入库。

        如果同名同 checksum 的文档已存在，跳过重复摄入。

        ``pre_registered=True`` 用于后台任务：文档记录已由
        :meth:`register_pending` 创建，处理过程只更新其状态。
        """
        import pathlib
        path = pathlib.Path(filepath)
        display_filename = filename or path.name
        doc_id = doc_id or str(uuid.uuid4())
        file_size = path.stat().st_size
        qdrant_written = False

        if not pre_registered:
            # 0. 检查是否已有相同 checksum 的文档（去重）
            checksum = await asyncio.to_thread(self._checksum, path)
            existing = await self._find_by_checksum(checksum)
            if existing is not None:
                logger.info("跳过重复摄入: %s (doc_id=%s)", display_filename, existing.id)
                return IngestionResult(
                    doc_id=existing.id,
                    filename=existing.filename,
                    chunk_count=existing.chunk_count,
                    status=DocumentStatus(existing.status),
                    error=existing.error,
                )

            # 1. 创建文档记录
            async with get_session() as session:
                doc = Document(
                    id=doc_id,
                    filename=display_filename,
                    file_type=path.suffix.lower(),
                    file_size=file_size,
                    checksum=checksum,
                    status=DocumentStatus.parsing,
                )
                session.add(doc)
                await session.commit()

        try:
            if pre_registered:
                await self._update_status(doc_id, DocumentStatus.parsing)
            # 2. 解析
            try:
                parsed: ParsedDocument = await asyncio.to_thread(self._parser.parse, path)
            except Exception as e:
                raise DocumentParseError(f"文档解析失败: {e}") from e

            # 3. 更新状态 → chunking
            await self._update_status(doc_id, DocumentStatus.chunking)

            # 3.5 图片页：视觉识别（识别成功回填页面文本），再生成完整性提示
            recognized = await self._recognize_image_pages(path, parsed)
            notes = _build_extraction_notes(parsed, recognized)

            # 4. 分块
            chunks = await asyncio.to_thread(
                self._chunker.chunk_pages,
                parsed.pages,
                display_filename,
            )
            if not chunks:
                raise DocumentParseError("文档解析后无有效文本内容")

            # 5. 更新状态 → embedding
            await self._update_status(doc_id, DocumentStatus.embedding)

            # 6. 批量向量化
            texts = [c.text for c in chunks]
            try:
                vectors = await self._embedder.embed(texts)
            except Exception as e:
                raise EmbeddingError(f"向量化失败: {e}") from e
            self._validate_vectors(vectors, expected_count=len(chunks))

            # 7. 写入 Qdrant
            try:
                await self._qdrant.ensure_collection()
                chunks_with_vectors = [
                    (c.text, vec, c.page_index + 1)
                    for c, vec in zip(chunks, vectors)
                ]
                count = await self._qdrant.upsert_chunks(
                    doc_id=doc_id,
                    filename=display_filename,
                    chunks=chunks_with_vectors,
                )
                qdrant_written = count > 0
            except QdrantError:
                raise
            except Exception as e:
                raise QdrantError(f"向量库写入失败: {e}") from e

            # 8. 更新文档记录 → indexed（清除上一次失败留下的报错）
            await self._update_status(
                doc_id,
                DocumentStatus.indexed,
                chunk_count=count,
                extraction_notes=notes,
                clear_error=True,
            )

            logger.info("摄入完成: %s → %d chunks (doc_id=%s)", display_filename, count, doc_id)
            return IngestionResult(
                doc_id=doc_id,
                filename=display_filename,
                chunk_count=count,
                status=DocumentStatus.indexed,
            )

        except Exception as e:
            logger.exception("摄入失败: %s", path.name)
            if qdrant_written:
                try:
                    await self._qdrant.delete_by_doc_id(doc_id)
                except Exception:
                    logger.exception("清理失败的 Qdrant chunks 失败: doc_id=%s", doc_id)
            await self._update_status(doc_id, DocumentStatus.failed, error=str(e))
            return IngestionResult(
                doc_id=doc_id,
                filename=path.name,
                chunk_count=0,
                status=DocumentStatus.failed,
                error=str(e),
            )

    def _validate_vectors(self, vectors, *, expected_count: int) -> None:
        """拒绝数量、维度或数值异常的 embedding，避免静默截断或污染向量库。"""
        import math
        from numbers import Real

        if not isinstance(vectors, (list, tuple)) or len(vectors) != expected_count:
            actual = len(vectors) if hasattr(vectors, "__len__") else "unknown"
            raise EmbeddingError(
                f"向量数量与文本块不一致（期望 {expected_count}，实际 {actual}）"
            )

        dimension = self._embedder.dimension
        if not isinstance(dimension, int) or dimension <= 0:
            raise EmbeddingError("Embedding 维度配置无效")
        for idx, vector in enumerate(vectors):
            if not isinstance(vector, (list, tuple)) or len(vector) != dimension:
                actual = len(vector) if hasattr(vector, "__len__") else "unknown"
                raise EmbeddingError(
                    f"第 {idx} 个向量维度不匹配（期望 {dimension}，实际 {actual}）"
                )
            if not all(isinstance(value, Real) and math.isfinite(value) for value in vector):
                raise EmbeddingError(f"第 {idx} 个向量包含无效数值")

    async def delete_document(self, doc_id: str) -> bool:
        """删除文档：先删 Qdrant 中的 chunks，再删 Postgres 记录。"""
        from sqlalchemy import delete as sa_delete

        # 先删 Qdrant
        await self._qdrant.delete_by_doc_id(doc_id)

        # 再删 Postgres
        async with get_session() as session:
            result = await session.execute(
                sa_delete(Document).where(Document.id == doc_id)
            )
            await session.commit()
            return result.rowcount > 0

    async def reingest(
        self,
        doc_id: str,
        filepath: str,
        *,
        filename: str | None = None,
    ) -> IngestionResult:
        """重新摄入已有文档，成功建立新索引后才删除旧数据。"""
        registered = await self.register_pending(filepath, filename=filename)
        # 内容未变化时 register_pending 会返回原文档，不能把它误删掉。
        if registered.status != DocumentStatus.pending:
            return registered

        result = await self.ingest_file(
            filepath,
            doc_id=registered.doc_id,
            filename=filename,
            pre_registered=True,
        )
        if result.status == DocumentStatus.indexed and result.doc_id != doc_id:
            # 旧文档仍可服务，直到新文档完整写入并标记 indexed。
            await self._qdrant.delete_by_doc_id(doc_id)
            from sqlalchemy import delete as sa_delete

            async with get_session() as session:
                await session.execute(sa_delete(Document).where(Document.id == doc_id))
                await session.commit()
        return result

    async def _recognize_image_pages(
        self, path, parsed: ParsedDocument
    ) -> dict[int, str]:
        """对纯图片页跑视觉识别，把识别文本回填进 parsed.pages。

        返回 {页码: 识别文本}；视觉客户端未配置或单页识别失败时，
        对应页保持空串并留在"未提取"标注里。
        """
        if not parsed.image_only_pages:
            return {}

        from app.ingestion.page_images import collect_page_images
        from app.llm.vision import get_vision_client

        client = get_vision_client()
        if client is None:
            return {}

        images = await asyncio.to_thread(
            collect_page_images,
            path,
            parsed.image_only_pages,
            settings.vision_max_pages,
        )

        recognized: dict[int, str] = {}
        for page_no, pictures in images.items():
            texts: list[str] = []
            for blob, mime in pictures:
                text = await client.extract_text(blob, mime, page_no=page_no)
                if text:
                    texts.append(text)
            if texts:
                recognized[page_no] = "\n\n".join(texts)

        for page_no, text in recognized.items():
            if 1 <= page_no <= len(parsed.pages):
                parsed.pages[page_no - 1] = text
        return recognized

    async def _find_by_checksum(self, checksum: str) -> Document | None:
        """按 checksum 查找已存在的文档记录。"""
        from sqlalchemy import select
        async with get_session() as session:
            result = await session.execute(
                select(Document).where(Document.checksum == checksum)
            )
            return result.scalar_one_or_none()

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
        extraction_notes: str | None = None,
        clear_error: bool = False,
    ) -> None:
        from sqlalchemy import update

        values: dict = {"status": status}
        if chunk_count is not None:
            values["chunk_count"] = chunk_count
        # error 为 None 表示"不改动"；要清除须显式 clear_error。
        # 否则重摄入成功的文档会继续挂着上一次失败的报错文案。
        if clear_error:
            values["error"] = None
        elif error is not None:
            values["error"] = error
        if extraction_notes is not None:
            values["extraction_notes"] = extraction_notes

        async with get_session() as session:
            await session.execute(
                update(Document).where(Document.id == doc_id).values(**values)
            )
            await session.commit()


_pipeline: IngestionPipeline | None = None


def _build_extraction_notes(
    parsed: ParsedDocument,
    recognized: dict[int, str] | None = None,
) -> str | None:
    """图片页处理结果的用户可读提示：已识别与未提取分开标注。"""
    recognized = recognized or {}
    done = sorted(p for p in parsed.image_only_pages if p in recognized)
    remaining = sorted(p for p in parsed.image_only_pages if p not in recognized)

    parts: list[str] = []
    if done:
        parts.append(f"第 {'、'.join(map(str, done))} 页图片内容已识别")
    if remaining:
        parts.append(
            f"第 {'、'.join(map(str, remaining))} 页为图片页（扫描件或纯图片），文字未提取"
        )
    return "；".join(parts) if parts else None


def get_pipeline() -> IngestionPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = IngestionPipeline()
    return _pipeline
