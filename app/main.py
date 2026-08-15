from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import chat, health
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时执行：未来在这里加载 embedding 模型、连接 Qdrant/Postgres 等
    yield
    # 关闭时执行：清理资源


def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{settings.app_name} — 知识库问答系统",
        description="公司个人知识库问答系统（RAG）",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(health.router, tags=["health"])
    app.include_router(chat.router, tags=["chat"])
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
