from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import admin, auth, chat, conversations, documents, health
from app.config import settings
from app.errors import register_exception_handlers
from app.llm.base import get_llm_client
from app.observability.logging import setup_logging
from app.observability.middleware import RequestTraceMiddleware
from app.rag.rag_service import RAGService
from app.storage.qdrant import get_qdrant_store
from app.storage.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    _warn_insecure_secret()
    client = get_llm_client()
    app.state.llm_client = client
    qdrant = get_qdrant_store()
    try:
        await qdrant.ensure_collection()
        rag_service = RAGService(llm_client=client)
    except Exception:
        rag_service = None
    app.state.rag_service = rag_service
    try:
        await init_db()
    except Exception:
        pass
    try:
        yield
    finally:
        await client.aclose()
        import app.storage.qdrant as _qdrant_mod
        _qdrant_mod._store = None
        app.state.llm_client = None
        app.state.rag_service = None


def _warn_insecure_secret() -> None:
    """非 debug 模式下使用默认 jwt_secret 是严重安全风险，打印警告。"""
    if not settings.debug and settings.jwt_is_default_secret:
        import logging
        logging.getLogger("app").warning(
            "⚠️ ZHIYUAN_JWT_SECRET 仍为默认值！生产环境必须设置，否则可伪造任意用户令牌。"
        )


def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{settings.app_name} — 知识库问答系统",
        description="公司个人知识库问答系统（RAG）",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(RequestTraceMiddleware)
    register_exception_handlers(app)
    app.include_router(health.router, tags=["health"])
    app.include_router(auth.router)
    app.include_router(chat.router, tags=["chat"])
    app.include_router(conversations.router)
    app.include_router(documents.router, tags=["documents"])
    app.include_router(admin.router)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
