"""Postgres 数据模型：文档注册表。

记录每个上传文档的元数据、处理状态、checksum（去重）。
chunks 不存这里（在 Qdrant），这里只追踪文档级信息。
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class DocumentStatus(str, enum.Enum):
    pending = "pending"
    parsing = "parsing"
    chunking = "chunking"
    embedding = "embedding"
    indexed = "indexed"
    failed = "failed"


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Document(Base):
    """文档注册表 —— 记录每个上传的文档及其处理状态。"""
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(20))
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[DocumentStatus] = mapped_column(
        SAEnum(DocumentStatus), default=DocumentStatus.pending
    )
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 内容完整性提示，如"第 3、5 页为图片页（扫描件），文字未提取"
    extraction_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    def __repr__(self) -> str:
        return f"<Document {self.filename} [{self.status}]>"
