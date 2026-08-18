"""文档管理 API：上传、列表、删除。"""

from __future__ import annotations

import logging
import tempfile
import pathlib

from fastapi import APIRouter, UploadFile, File, HTTPException
from sqlalchemy import select

from app.ingestion.parser import SUPPORTED_EXTENSIONS
from app.ingestion.pipeline import get_pipeline
from app.storage.postgres import Document
from app.storage.session import get_session

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    """上传文档并摄入。

    接收文件 → 保存临时文件 → 调用摄入管线 → 返回结果。
    当前是同步处理（等返回）；阶段 4 会改成后台任务 + 状态轮询。
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    ext = pathlib.Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"不支持的文件格式: {ext}（支持: {', '.join(sorted(SUPPORTED_EXTENSIONS))}）",
        )

    # 保存到临时文件
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        pipeline = get_pipeline()
        result = await pipeline.ingest_file(tmp_path)
        if result.status.value == "failed":
            raise HTTPException(status_code=500, detail=f"摄入失败: {result.error}")
        return {
            "doc_id": result.doc_id,
            "filename": result.filename,
            "chunk_count": result.chunk_count,
            "status": result.status.value,
        }
    finally:
        pathlib.Path(tmp_path).unlink(missing_ok=True)


@router.get("/documents")
async def list_documents():
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
                "created_at": d.created_at.isoformat(),
            }
            for d in docs
        ]


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    """删除文档及其所有 chunks。"""
    pipeline = get_pipeline()
    deleted = await pipeline.delete_document(doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"deleted": True, "doc_id": doc_id}
