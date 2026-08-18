"""Postgres 异步会话管理。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.storage.postgres import Base

_engine: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    from app.config import settings
    global _engine
    if _engine is None:
        engine = create_async_engine(settings.database_url, echo=settings.debug)
        _engine = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return _engine


async def init_db() -> None:
    """创建所有表（开发阶段用；生产用 Alembic 迁移）。"""
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.config import settings

    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


async def get_session() -> AsyncSession:
    """获取异步数据库会话。"""
    sessionmaker = get_engine()
    return sessionmaker()
