"""HTTP 请求追踪中间件。

每个请求分配唯一 request_id，注入到 structlog 上下文，
记录请求方法、路径、状态码、延迟。
"""

from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger("app.request")


class RequestTraceMiddleware(BaseHTTPMiddleware):
    """为每个 HTTP 请求注入追踪上下文。"""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        start = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.error(
                "request_failed",
                status=500,
                elapsed_ms=round(elapsed_ms, 2),
            )
            raise

        elapsed_ms = (time.perf_counter() - start) * 1000

        logger.info(
            "request_completed",
            status=response.status_code,
            elapsed_ms=round(elapsed_ms, 2),
        )

        response.headers["X-Request-ID"] = request_id
        return response
