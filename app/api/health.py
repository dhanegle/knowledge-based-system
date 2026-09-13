"""存活与就绪探针。

``/health`` 保留为兼容旧客户端的轻量存活接口；``/health/ready`` 会对
数据库和 Qdrant 做短超时探测，适合负载均衡器和编排系统使用。
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.storage.session import get_session

router = APIRouter()

_PROBE_TIMEOUT_SECONDS = 2.0
_REQUIRED_DEPENDENCIES = ("database", "qdrant", "rag", "llm")


def _status_snapshot(request: Request) -> dict[str, dict[str, Any]]:
    statuses = getattr(request.app.state, "dependency_status", None)
    if not isinstance(statuses, dict):
        return {
            "llm": {"status": "unknown", "configured": settings.llm_configured},
            "qdrant": {"status": "unknown"},
            "database": {"status": "unknown"},
            "rag": {"status": "unknown"},
        }
    return statuses


def _public_statuses(statuses: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return health details without exposing exception messages or secrets."""
    public: dict[str, dict[str, Any]] = {}
    for name, value in statuses.items():
        item = {"status": value.get("status", "unknown")}
        if "configured" in value:
            item["configured"] = bool(value["configured"])
        if value.get("error"):
            item["error"] = value["error"]
        public[name] = item
    return public


async def _probe_database() -> None:
    """Run a minimal database query with a bounded timeout."""
    async with get_session() as session:
        await asyncio.wait_for(session.execute(text("SELECT 1")), _PROBE_TIMEOUT_SECONDS)


async def _probe_qdrant(request: Request) -> None:
    """Probe the Qdrant client without creating a new global store."""
    store = getattr(request.app.state, "qdrant_store", None)
    if store is None:
        raise RuntimeError("qdrant store is not initialized")

    # QdrantStore intentionally keeps the SDK client private. Use a future
    # health_check hook when available, otherwise call the SDK's read-only
    # collection endpoint. Test doubles without an SDK client use startup state.
    check = getattr(store, "health_check", None)
    if callable(check):
        result = check()
        if hasattr(result, "__await__"):
            await asyncio.wait_for(result, _PROBE_TIMEOUT_SECONDS)
        return

    client = getattr(store, "_client", None)
    get_collections = getattr(client, "get_collections", None)
    if callable(get_collections):
        await asyncio.wait_for(get_collections(), _PROBE_TIMEOUT_SECONDS)
        return

    statuses = _status_snapshot(request)
    if statuses.get("qdrant", {}).get("status") != "ok":
        raise RuntimeError("qdrant startup check failed")


async def _probe_dependencies(request: Request) -> dict[str, dict[str, Any]]:
    statuses = _status_snapshot(request)
    results = await asyncio.gather(
        _probe_database(),
        _probe_qdrant(request),
        return_exceptions=True,
    )

    for name, result in zip(("database", "qdrant"), results, strict=True):
        if isinstance(result, Exception):
            statuses[name] = {"status": "error", "error": type(result).__name__}
        else:
            statuses[name] = {"status": "ok"}

    # RAG is usable only while both its Qdrant dependency and service object
    # are available. This also lets readiness recover after a transient probe
    # failure without restarting the process.
    rag_service = getattr(request.app.state, "rag_service", None)
    if statuses.get("qdrant", {}).get("status") != "ok" or rag_service is None:
        statuses["rag"] = {"status": "unavailable"}
    else:
        statuses["rag"] = {"status": "ok"}

    request.app.state.dependency_status = statuses
    request.app.state.ready = all(
        statuses.get(name, {}).get("status") == "ok" for name in _REQUIRED_DEPENDENCIES
    ) and statuses.get("llm", {}).get("status") != "error"
    return statuses


@router.get("/health")
async def health(request: Request):
    """Backward-compatible liveness response with dependency information."""
    statuses = _status_snapshot(request)
    return {
        "status": "ok",
        "app": settings.app_name,
        "llm_configured": settings.llm_configured,
        "ready": bool(getattr(request.app.state, "ready", False)),
        "dependencies": _public_statuses(statuses),
    }


@router.get("/health/live")
async def liveness(request: Request):
    """Process liveness probe; it does not require backing services."""
    return {"status": "ok", "app": settings.app_name}


@router.get("/health/ready")
async def readiness(request: Request):
    """Readiness probe with bounded database and Qdrant checks."""
    statuses = await _probe_dependencies(request)
    ready = bool(getattr(request.app.state, "ready", False))
    body = {
        "status": "ok" if ready else "unavailable",
        "app": settings.app_name,
        "ready": ready,
        "dependencies": _public_statuses(statuses),
    }
    return JSONResponse(status_code=200 if ready else 503, content=body)
