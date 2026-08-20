"""错误处理 + 缓存测试。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient

from app import main
from app.cache import _cache_key, get_cached_answer, reset_redis, set_cached_answer
from app.config import settings
from app.errors import (
    DocumentNotFoundError,
    DuplicateDocumentError,
    EmbeddingError,
    LLMError,
    LLMTimeoutError,
    QdrantError,
    ZhiyuanError,
)
from app.llm.base import StubLLMClient


def _mock_infra(monkeypatch):
    class FakeQdrant:
        async def ensure_collection(self):
            pass

        async def search(self, query_vector, top_k=20, doc_ids=None):
            return []

        async def close(self):
            pass

    fake = FakeQdrant()
    import app.storage.qdrant as qdrant_mod
    monkeypatch.setattr(qdrant_mod, "_store", fake)

    from app.embedding.base import StubEmbeddingService
    import app.embedding.base as emb_mod
    monkeypatch.setattr(emb_mod, "_embedding_service", StubEmbeddingService(dim=768))

    return fake


def _setup_test_db(monkeypatch):
    import uuid as _uuid
    import app.storage.session as session_mod
    session_mod._engine = None
    monkeypatch.setattr(
        settings, "database_url",
        f"sqlite+aiosqlite:///file:{_uuid.uuid4().hex}?mode=memory&cache=shared",
    )


def _create_test_user(client):
    resp = client.post(
        "/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "password123",
        },
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    return token


def _reset_cache():
    import app.cache as cache_mod
    cache_mod._redis_checked = True
    cache_mod._redis_client = None


def test_error_hierarchy():
    """所有业务异常都继承 ZhiyuanError，且有 error_code 和 http_status。"""
    for exc_cls in [
        DocumentNotFoundError,
        DuplicateDocumentError,
        EmbeddingError,
        LLMError,
        LLMTimeoutError,
        QdrantError,
    ]:
        exc = exc_cls("test")
        assert isinstance(exc, ZhiyuanError)
        assert exc.error_code
        assert exc.http_status >= 400


def test_document_not_found_error_returns_404(monkeypatch):
    monkeypatch.setattr(main, "get_llm_client", lambda: StubLLMClient())
    _mock_infra(monkeypatch)
    _setup_test_db(monkeypatch)

    with TestClient(main.create_app()) as client:
        token = _create_test_user(client)
        resp = client.get(
            "/documents/nonexistent-id",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404
        body = resp.json()
        assert body["ok"] is False
        assert body["error_code"] == "document_not_found"


def test_unhandled_error_returns_500(monkeypatch):
    """未知异常被全局处理器捕获，返回 500 且不泄露内部信息。"""
    monkeypatch.setattr(main, "get_llm_client", lambda: StubLLMClient())
    _mock_infra(monkeypatch)
    _setup_test_db(monkeypatch)

    from fastapi import APIRouter

    crash_router = APIRouter()

    @crash_router.get("/_test/crash")
    async def crash():
        raise RuntimeError("internal secret leak")

    original_create = main.create_app

    def patched_create():
        app = original_create()
        app.include_router(crash_router)
        return app

    monkeypatch.setattr(main, "create_app", patched_create)

    with TestClient(patched_create(), raise_server_exceptions=False) as client:
        resp = client.get("/_test/crash")
        assert resp.status_code == 500
        body = resp.json()
        assert body["ok"] is False
        assert "internal secret leak" not in json.dumps(body)
        assert body["error_code"] == "internal_error"


# ---- Cache tests ----


@pytest.mark.asyncio
async def test_cache_key_is_deterministic():
    k1 = _cache_key("hello", None, "user1")
    k2 = _cache_key("hello", None, "user1")
    assert k1 == k2


@pytest.mark.asyncio
async def test_cache_key_differs_for_different_questions():
    k1 = _cache_key("hello", None, "user1")
    k2 = _cache_key("world", None, "user1")
    assert k1 != k2


@pytest.mark.asyncio
async def test_cache_key_normalizes_doc_ids_order():
    k1 = _cache_key("question", ["a", "b"], "user1")
    k2 = _cache_key("question", ["b", "a"], "user1")
    assert k1 == k2


@pytest.mark.asyncio
async def test_cache_key_differs_for_different_users():
    """不同用户的相同问题不应命中同一缓存，防止对话串通。"""
    k1 = _cache_key("hello", None, "user1")
    k2 = _cache_key("hello", None, "user2")
    assert k1 != k2


@pytest.mark.asyncio
async def test_cache_miss_returns_none_without_redis():
    """Redis 不可用时，缓存查询返回 None 而不报错。"""
    await reset_redis()
    # Force redis to be unavailable
    import app.cache as cache_mod
    cache_mod._redis_checked = True
    cache_mod._redis_client = None

    result = await get_cached_answer("test question", None, user_id="testuser")
    assert result is None

    # set should also not raise
    await set_cached_answer("test", {"answer": "hello"}, None, user_id="testuser")
