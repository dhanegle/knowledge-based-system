"""文档管理 API：上传、列表、详情、删除、重新摄入。"""

from __future__ import annotations

import logging
import pathlib
import tempfile

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.auth.dependencies import get_current_admin, get_current_user
from app.auth.models import User
from app.cache import invalidate_doc_cache
from app.config import settings
from app.errors import DocumentNotFoundError, DocumentParseError
from app.ingestion.parser import SUPPORTED_EXTENSIONS
from app.ingestion.pipeline import get_pipeline
from app.storage.postgres import Document
from app.storage.session import get_session

router = APIRouter()
logger = logging.getLogger(__name__)

_UPLOAD_READ_BLOCK_SIZE = 1024 * 1024


async def _save_upload_to_temp(file: UploadFile, suffix: str) -> str:
    """将上传内容以固定大小的块写入临时文件，并执行大小上限检查。"""
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name
            total = 0
            max_size = settings.max_upload_size
            while True:
                # 多读一个字节以可靠检测超过上限的文件，同时始终保持有界内存。
                read_size = min(_UPLOAD_READ_BLOCK_SIZE, max_size - total + 1)
                chunk = await file.read(read_size)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_size:
                    raise DocumentParseError(
                        f"文件过大，大小不能超过 {max_size} 字节"
                    )
                tmp.write(chunk)
        return tmp_path
    except Exception:
        if tmp_path:
            pathlib.Path(tmp_path).unlink(missing_ok=True)
        raise


async def _run_ingestion(tmp_path: str, doc_id: str, filename: str) -> None:
    """Run ingestion after the upload response and always remove the temp file."""
    try:
        result = await get_pipeline().ingest_file(
            tmp_path,
            doc_id=doc_id,
            filename=filename,
            pre_registered=True,
        )
        if result.status.value == "indexed":
            # A newly indexed document changes the answer set for queries that
            # search the whole collection.
            await invalidate_doc_cache(doc_id)
    except Exception:
        # ingest_file records expected failures in the document row; this
        # catches infrastructure errors while keeping the background task from
        # producing an unhandled exception after the response was sent.
        logger.exception("后台文档摄入任务失败: doc_id=%s", doc_id)
    finally:
        pathlib.Path(tmp_path).unlink(missing_ok=True)


@router.post("/documents/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_admin),
):
    """上传文档并摄入。

    接收文件 → 保存临时文件 → 调用摄入管线 → 返回结果。
    相同 checksum 的文件会自动跳过重复摄入。
    """
    if not file.filename:
        raise DocumentParseError("文件名不能为空")

    ext = pathlib.Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise DocumentParseError(
            f"不支持的文件格式: {ext}（支持: {', '.join(sorted(SUPPORTED_EXTENSIONS))}）"
        )

    tmp_path = await _save_upload_to_temp(file, ext)

    try:
        pipeline = get_pipeline()
        result = await pipeline.register_pending(tmp_path, filename=file.filename)
    except Exception:
        pathlib.Path(tmp_path).unlink(missing_ok=True)
        raise

    # A checksum hit is already complete (or already being processed); do not
    # enqueue a duplicate task and remove this request's temporary file.
    if result.status.value != "pending":
        pathlib.Path(tmp_path).unlink(missing_ok=True)
        return {
            "doc_id": result.doc_id,
            "filename": result.filename,
            "chunk_count": result.chunk_count,
            "status": result.status.value,
            "error": result.error,
        }

    background_tasks.add_task(_run_ingestion, tmp_path, result.doc_id, result.filename)
    return JSONResponse(
        status_code=202,
        content={
            "doc_id": result.doc_id,
            "filename": result.filename,
            "chunk_count": 0,
            "status": result.status.value,
        },
    )


@router.get("/documents")
async def list_documents(current_user: User = Depends(get_current_user)):
    """列出所有文档。"""
    async with get_session() as session:
        result = await session.execute(select(Document).order_by(Document.created_at.desc()))
        docs = result.scalars().all()
        return [
            {
                "id": d.id,
                "filename": d.filename,
                "file_type": d.file_type,
                "file_size": d.file_size,
                "status": d.status.value,
                "chunk_count": d.chunk_count,
                "error": d.error,
                "extraction_notes": d.extraction_notes,
                "created_at": d.created_at.isoformat(),
                "updated_at": d.updated_at.isoformat() if d.updated_at else None,
            }
            for d in docs
        ]


@router.get("/documents/{doc_id}")
async def get_document(
    doc_id: str,
    current_user: User = Depends(get_current_user),
):
    """查询单个文档详情（含处理状态，供前端轮询摄入进度）。"""
    async with get_session() as session:
        result = await session.execute(select(Document).where(Document.id == doc_id))
        doc = result.scalar_one_or_none()
        if doc is None:
            raise DocumentNotFoundError("文档不存在")
        return {
            "id": doc.id,
            "filename": doc.filename,
            "file_type": doc.file_type,
            "file_size": doc.file_size,
            "checksum": doc.checksum,
            "status": doc.status.value,
            "chunk_count": doc.chunk_count,
            "error": doc.error,
            "extraction_notes": doc.extraction_notes,
            "created_at": doc.created_at.isoformat(),
            "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
        }


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: str,
    current_user: User = Depends(get_current_admin),
):
    """删除文档及其所有 chunks（先删 Qdrant，再删 Postgres，再清缓存）。"""
    pipeline = get_pipeline()
    deleted = await pipeline.delete_document(doc_id)
    if not deleted:
        raise DocumentNotFoundError("文档不存在")
    # 文档删除后，相关查询缓存应失效
    await invalidate_doc_cache(doc_id)
    return {"deleted": True, "doc_id": doc_id}


@router.post("/documents/{doc_id}/reingest")
async def reingest_document(
    doc_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_admin),
):
    """重新摄入文档：删除旧 chunks 后用新文件重新摄入。

    用于文档内容变更后更新向量索引。
    """
    if not file.filename:
        raise DocumentParseError("文件名不能为空")

    ext = pathlib.Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise DocumentParseError(f"不支持的文件格式: {ext}")

    tmp_path = await _save_upload_to_temp(file, ext)

    try:
        pipeline = get_pipeline()
        result = await pipeline.reingest(doc_id, tmp_path, filename=file.filename)
        # 重新摄入后旧缓存失效
        await invalidate_doc_cache(doc_id)
        return {
            "doc_id": result.doc_id,
            "filename": result.filename,
            "chunk_count": result.chunk_count,
            "status": result.status.value,
        }
    finally:
        pathlib.Path(tmp_path).unlink(missing_ok=True)
