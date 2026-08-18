"""统一异常体系 + FastAPI 异常处理器。

所有业务异常继承 ZhiyuanError，带有 error_code 和 http_status。
异常处理器统一返回 {"ok": false, "error": ..., "error_code": ...} 格式。
"""

from __future__ import annotations

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = structlog.get_logger("app.errors")


class ZhiyuanError(Exception):
    """所有业务异常基类。"""

    error_code: str = "internal_error"
    http_status: int = 500

    def __init__(self, message: str, *, detail: str | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail


class DocumentParseError(ZhiyuanError):
    error_code = "document_parse_error"
    http_status = 422


class EmbeddingError(ZhiyuanError):
    error_code = "embedding_error"
    http_status = 502


class LLMTimeoutError(ZhiyuanError):
    error_code = "llm_timeout"
    http_status = 504


class LLMError(ZhiyuanError):
    error_code = "llm_error"
    http_status = 502


class QdrantError(ZhiyuanError):
    error_code = "qdrant_error"
    http_status = 503


class DocumentNotFoundError(ZhiyuanError):
    error_code = "document_not_found"
    http_status = 404


class DuplicateDocumentError(ZhiyuanError):
    error_code = "duplicate_document"
    http_status = 409


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器。"""

    @app.exception_handler(ZhiyuanError)
    async def handle_zhiyuan_error(request: Request, exc: ZhiyuanError):
        logger.warning(
            "business_error",
            error_code=exc.error_code,
            message=exc.message,
            path=request.url.path,
        )
        body = {"ok": False, "error": exc.message, "error_code": exc.error_code}
        if exc.detail:
            body["detail"] = exc.detail
        return JSONResponse(status_code=exc.http_status, content=body)

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        logger.exception(
            "unhandled_error",
            error=str(exc),
            path=request.url.path,
        )
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": "服务器内部错误",
                "error_code": "internal_error",
            },
        )
