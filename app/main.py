import logging
from contextlib import asynccontextmanager
from typing import Any

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

logger = logging.getLogger("app")


def _initial_dependency_status() -> dict[str, dict[str, Any]]:
    """Return a fresh dependency status snapshot for a newly created app."""
    return {
        "llm": {"status": "starting", "configured": settings.llm_configured},
        "qdrant": {"status": "starting"},
        "database": {"status": "starting"},
        "rag": {"status": "starting"},
    }


def _mark_dependency(
    statuses: dict[str, dict[str, Any]],
    name: str,
    status: str,
    *,
    error: Exception | None = None,
    **extra: Any,
) -> None:
    """Update a dependency status while keeping public error details safe."""
    value: dict[str, Any] = {"status": status, **extra}
    if error is not None:
        # Keep credentials and connection strings out of health responses. The
        # full exception is still available in the structured startup log.
        value["error"] = type(error).__name__
    statuses[name] = value


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    _validate_jwt_secret()

    statuses = _initial_dependency_status()
    app.state.dependency_status = statuses
    app.state.ready = False
    app.state.llm_client = None
    app.state.qdrant_store = None
    app.state.rag_service = None

    client = None
    qdrant = None
    try:
        try:
            client = get_llm_client()
            app.state.llm_client = client
            _mark_dependency(
                statuses,
                "llm",
                "ok" if settings.llm_configured else "unconfigured",
                configured=settings.llm_configured,
            )
        except Exception as exc:
            logger.exception("llm_initialization_failed")
            _mark_dependency(statuses, "llm", "error", error=exc, configured=False)

        try:
            qdrant = get_qdrant_store()
            app.state.qdrant_store = qdrant
            await qdrant.ensure_collection()
            _mark_dependency(statuses, "qdrant", "ok")
        except Exception as exc:
            logger.exception("qdrant_initialization_failed")
            _mark_dependency(statuses, "qdrant", "error", error=exc)

        try:
            await init_db()
            _mark_dependency(statuses, "database", "ok")
        except Exception as exc:
            logger.exception("database_initialization_failed")
            _mark_dependency(statuses, "database", "error", error=exc)

        if client is not None and statuses["qdrant"]["status"] == "ok":
            try:
                app.state.rag_service = RAGService(
                    llm_client=client, chat_model=getattr(client, "chat_model", None)
                )
                _mark_dependency(statuses, "rag", "ok")
            except Exception as exc:
                logger.exception("rag_initialization_failed")
                _mark_dependency(statuses, "rag", "error", error=exc)
        else:
            _mark_dependency(statuses, "rag", "unavailable")

        app.state.ready = _startup_ready(statuses)
        yield
    finally:
        if qdrant is not None:
            try:
                await qdrant.close()
            except Exception:
                logger.exception("qdrant_shutdown_failed")
        import app.storage.qdrant as _qdrant_mod
        _qdrant_mod._store = None
        import app.embedding.base as _embedding_mod
        embedding = _embedding_mod._embedding_service
        if embedding is not None:
            try:
                await embedding.close()
            except Exception:
                logger.exception("embedding_shutdown_failed")
        _embedding_mod._embedding_service = None
        if client is not None:
            try:
                await client.aclose()
            except Exception:
                logger.exception("llm_shutdown_failed")
        try:
            import app.llm.vision as _vision_mod
            from app.llm.vision import reset_vision_client

            vision = _vision_mod._client
            if vision is not None:
                await vision.aclose()
            reset_vision_client()
        except Exception:
            logger.exception("vision_shutdown_failed")
        try:
            from app.retrieval.reranker import close_reranker

            await close_reranker()
        except Exception:
            logger.exception("reranker_shutdown_failed")
        try:
            from app.cache import reset_redis

            await reset_redis()
        except Exception:
            logger.exception("redis_shutdown_failed")
        app.state.llm_client = None
        app.state.qdrant_store = None
        app.state.rag_service = None
        app.state.ready = False


def _validate_jwt_secret() -> None:
    """Refuse to start production with a missing or known default JWT key."""
    if settings.debug:
        return
    if not settings.jwt_secret.strip() or settings.jwt_is_default_secret:
        raise RuntimeError(
            "ZHIYUAN_JWT_SECRET must be set to a strong, non-default value when debug is disabled"
        )


def _startup_ready(statuses: dict[str, dict[str, Any]]) -> bool:
    """Whether startup completed all dependencies required by the RAG API."""
    return all(
        statuses[name].get("status") == "ok"
        for name in ("qdrant", "database", "rag", "llm")
    )


def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{settings.app_name} — 知识库问答系统",
        description="公司个人知识库问答系统（RAG）",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.dependency_status = _initial_dependency_status()
    app.state.ready = False
    app.state.llm_client = None
    app.state.qdrant_store = None
    app.state.rag_service = None
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
