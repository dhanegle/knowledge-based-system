"""摄入管线：失败文档的重试语义。

背景：checksum 去重如果对 failed 文档也短路，用户就无从恢复——
重新上传会走 register_pending，点「重新摄入」会走 reingest，
两条路都因「已存在同 checksum 文档」而早退，文件永远停在失败态。

本文件锁定两条不变式：
1. failed 文档允许重试（回到 pending，并清掉上一次的报错）；
2. indexed 文档仍然被去重（不允许重复摄入）。
"""

import hashlib
import tempfile
import uuid

from sqlalchemy import select

from app.config import settings


def _isolate(monkeypatch):
    """隔离 Qdrant / embedding / 数据库，避免触碰真实外部依赖。"""
    import app.embedding.base as emb_mod
    import app.storage.qdrant as qdrant_mod
    import app.storage.session as session_mod
    from app.embedding.base import StubEmbeddingService

    class FakeQdrant:
        async def ensure_collection(self):
            pass

        async def upsert_chunks(self, doc_id, filename, chunks):
            return len(list(chunks))

        async def search(self, query_vector, top_k=20, doc_ids=None):
            return []

        async def close(self):
            pass

    monkeypatch.setattr(qdrant_mod, "_store", FakeQdrant())
    monkeypatch.setattr(emb_mod, "_embedding_service", StubEmbeddingService(dim=768))

    session_mod._engine = None
    monkeypatch.setattr(
        settings,
        "database_url",
        # 文件型 SQLite：共享内存库在 Windows + aiosqlite 下不稳，与 test_api 保持一致
        f"sqlite+aiosqlite:///{tempfile.gettempdir().replace(chr(92), '/')}"
        f"/zy_retry_{uuid.uuid4().hex}.db",
    )


async def _seed(tmp_path, *, status, chunk_count=0, error=None, content=b"retry me"):
    """写入一个指定状态的文档行，并返回与之 checksum 相同的文件路径。"""
    from app.storage.postgres import Document
    from app.storage.session import get_session, init_db

    await init_db()

    target = tmp_path / "r.docx"
    target.write_bytes(content)
    checksum = hashlib.sha256(content).hexdigest()

    async with get_session() as session:
        session.add(
            Document(
                id=f"doc-{status.value}",
                filename="r.docx",
                file_type=".docx",
                file_size=len(content),
                checksum=checksum,
                status=status,
                chunk_count=chunk_count,
                error=error,
            )
        )
        await session.commit()

    return target


async def test_failed_document_can_be_retried(monkeypatch, tmp_path):
    _isolate(monkeypatch)

    from app.ingestion.pipeline import IngestionPipeline
    from app.storage.postgres import Document, DocumentStatus
    from app.storage.session import get_session

    target = await _seed(
        tmp_path,
        status=DocumentStatus.failed,
        error="向量化失败: All connection attempts failed",
    )

    result = await IngestionPipeline().register_pending(str(target))

    assert result.status == DocumentStatus.pending, "失败文档必须允许重试"
    assert result.doc_id == "doc-failed", "重试应复用原 doc_id，而不是新建"

    async with get_session() as session:
        doc = (
            await session.execute(select(Document).where(Document.id == "doc-failed"))
        ).scalar_one()

    assert doc.status == DocumentStatus.pending
    assert doc.error is None, "重试时应清除上一次的报错文案"


async def test_indexed_document_is_still_deduplicated(monkeypatch, tmp_path):
    _isolate(monkeypatch)

    from app.ingestion.pipeline import IngestionPipeline
    from app.storage.postgres import DocumentStatus

    target = await _seed(tmp_path, status=DocumentStatus.indexed, chunk_count=7)

    result = await IngestionPipeline().register_pending(str(target))

    assert result.status == DocumentStatus.indexed, "已入库文档不应被重复摄入"
    assert result.chunk_count == 7
