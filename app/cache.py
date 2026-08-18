"""Redis 查询缓存。

对 RAG 查询结果做缓存：相同 question+doc_ids 在 TTL 内返回缓存回答。
Redis 不可用时自动降级（不缓存，不影响正常流程）。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import structlog

from app.config import settings

logger = structlog.get_logger("app.cache")

_redis_client = None
_redis_checked = False


def _get_redis():
    """惰性初始化 Redis 客户端，不可用时返回 None。"""
    global _redis_client, _redis_checked
    if _redis_checked:
        return _redis_client
    _redis_checked = True
    try:
        import redis.asyncio as aioredis

        _redis_client = aioredis.from_url(
            settings.redis_url, decode_responses=True, socket_connect_timeout=2
        )
        logger.info("redis_client_initialized", url=settings.redis_url)
    except Exception as e:
        logger.warning("redis_init_failed", error=str(e))
        _redis_client = None
    return _redis_client


async def reset_redis() -> None:
    """关闭并重置 Redis 客户端（测试用）。"""
    global _redis_client, _redis_checked
    if _redis_client is not None:
        try:
            await _redis_client.aclose()
        except Exception:
            pass
    _redis_client = None
    _redis_checked = False


def _cache_key(question: str, doc_ids: list[str] | None) -> str:
    """生成缓存键：hash(question + sorted(doc_ids))。"""
    raw = json.dumps(
        {"q": question.strip().lower(), "docs": sorted(doc_ids) if doc_ids else []},
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"zhiyuan:cache:ask:{digest}"


async def get_cached_answer(question: str, doc_ids: list[str] | None = None) -> dict[str, Any] | None:
    """从缓存获取查询结果，未命中或 Redis 不可用时返回 None。"""
    client = _get_redis()
    if client is None:
        return None
    try:
        key = _cache_key(question, doc_ids)
        raw = await client.get(key)
        if raw is None:
            return None
        result = json.loads(raw)
        logger.info("cache_hit", key=key[:32])
        return result
    except Exception as e:
        logger.warning("cache_get_failed", error=str(e))
        return None


async def set_cached_answer(
    question: str,
    answer: dict[str, Any],
    doc_ids: list[str] | None = None,
    ttl: int | None = None,
) -> None:
    """写入缓存，Redis 不可用时静默跳过。"""
    client = _get_redis()
    if client is None:
        return
    try:
        key = _cache_key(question, doc_ids)
        raw = json.dumps(answer, ensure_ascii=False)
        await client.set(key, raw, ex=ttl or settings.cache_ttl)
        logger.info("cache_set", key=key[:32], ttl=ttl or settings.cache_ttl)
    except Exception as e:
        logger.warning("cache_set_failed", error=str(e))
