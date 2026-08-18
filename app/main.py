from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import chat, documents, health
from app.config import settings
from app.llm.base import get_llm_client
from app.observability.logging import setup_logging
from app.observability.middleware import RequestTraceMiddleware
from app.rag.rag_service import RAGService
from app.storage.qdrant import get_qdrant_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
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
        yield
    finally:
        await client.aclose()
        import app.storage.qdrant as _qdrant_mod
        _qdrant_mod._store = None
        app.state.llm_client = None
        app.state.rag_service = None


def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{settings.app_name} — 知识库问答系统",
        description="公司个人知识库问答系统（RAG）",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(RequestTraceMiddleware)
    app.include_router(health.router, tags=["health"])
    app.include_router(chat.router, tags=["chat"])
    app.include_router(documents.router, tags=["documents"])
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
