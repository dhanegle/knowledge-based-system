from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import chat, documents, health
from app.config import settings
from app.llm.base import get_llm_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 在应用级别复用 LLM 客户端，避免每个请求都创建新的 HTTP 连接池。
    client = get_llm_client()
    app.state.llm_client = client
    try:
        # 未来可以在这里加载 embedding 模型、连接 Qdrant/Postgres 等。
        yield
    finally:
        await client.aclose()
        app.state.llm_client = None


def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{settings.app_name} — 知识库问答系统",
        description="公司个人知识库问答系统（RAG）",
        version="0.1.0",
        lifespan=lifespan,
    )
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
