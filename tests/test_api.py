import tempfile as _tempfile
from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from app import main
from app.config import settings
from app.llm.base import StubLLMClient


class RecordingLLMClient:
    def __init__(self, chunks: tuple[str, ...] = ("第一段", "第二段")):
        self.chunks = chunks
        self.closed = False

    async def stream(self, question: str, **_: str) -> AsyncIterator[str]:
        for chunk in self.chunks:
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


class FailingLLMClient:
    async def stream(self, question: str, **_: str) -> AsyncIterator[str]:
        raise RuntimeError("upstream details must not reach the client")
        yield question

    async def aclose(self) -> None:
        return None


def _mock_qdrant(monkeypatch):
    """Mock Qdrant store to avoid real connections in tests."""
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

    # Mock embedding service to avoid real API calls
    import app.embedding.base as emb_mod
    from app.embedding.base import StubEmbeddingService
    monkeypatch.setattr(emb_mod, "_embedding_service", StubEmbeddingService(dim=768))

    return fake


def _setup_test_db(monkeypatch):
    """Use in-memory SQLite for test isolation."""
    import uuid as _uuid

    import app.storage.session as session_mod
    session_mod._engine = None
    monkeypatch.setattr(
        settings, "database_url",
        # 文件型 SQLite（临时目录）：共享内存库在 Windows + aiosqlite 下
        # 连接回收后会报 "disk I/O error"，改用临时文件保证跨平台稳定。
        f"sqlite+aiosqlite:///{_tempfile.gettempdir().replace(chr(92), '/')}/zy_test_{_uuid.uuid4().hex}.db",
    )


def _reset_cache():
    """Disable Redis cache to avoid cross-test cache hits."""
    import app.cache as cache_mod
    cache_mod._redis_checked = True
    cache_mod._redis_client = None


def _create_test_user(client):
    """Register a test user and return the auth token."""
    resp = client.post(
        "/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "password123",
        },
    )
    assert resp.status_code == 201
    return resp.json()["access_token"]


def test_health_requires_all_llm_settings(monkeypatch):
    monkeypatch.setattr(main, "get_llm_client", lambda: StubLLMClient())
    monkeypatch.setattr(settings, "llm_base_url", "")
    monkeypatch.setattr(settings, "llm_api_key", "configured")
    monkeypatch.setattr(settings, "llm_model", "")
    _mock_qdrant(monkeypatch)

    with TestClient(main.create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["llm_configured"] is False


def test_health_reports_configured_when_all_llm_settings_exist(monkeypatch):
    monkeypatch.setattr(main, "get_llm_client", lambda: StubLLMClient())
    monkeypatch.setattr(settings, "llm_base_url", "https://example.test/v1")
    monkeypatch.setattr(settings, "llm_api_key", "configured")
    monkeypatch.setattr(settings, "llm_model", "test-model")
    _mock_qdrant(monkeypatch)

    with TestClient(main.create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["llm_configured"] is True


def test_ask_streams_tokens_and_closes_shared_client(monkeypatch):
    llm = RecordingLLMClient()
    monkeypatch.setattr(main, "get_llm_client", lambda: llm)
    _mock_qdrant(monkeypatch)
    _setup_test_db(monkeypatch)
    _reset_cache()

    with TestClient(main.create_app()) as client:
        token = _create_test_user(client)
        response = client.get(
            "/ask", params={"q": "你好"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert 'event: token\r\ndata: {"text": "第一段"}' in response.text
    assert 'event: token\r\ndata: {"text": "第二段"}' in response.text
    assert '"ok": true' in response.text
    assert llm.closed is True


def test_ask_emits_error_event_without_upstream_details(monkeypatch):
    monkeypatch.setattr(main, "get_llm_client", lambda: FailingLLMClient())
    _mock_qdrant(monkeypatch)
    _setup_test_db(monkeypatch)
    _reset_cache()

    with TestClient(main.create_app()) as client:
        token = _create_test_user(client)
        response = client.get(
            "/ask", params={"q": "hello"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert 'event: error\r\ndata: {"ok": false, "error": "LLM request failed"}' in response.text
    assert "upstream details must not reach" not in response.text
    assert "event: done" not in response.text


def test_ask_requires_question(monkeypatch):
    monkeypatch.setattr(main, "get_llm_client", lambda: StubLLMClient())
    _mock_qdrant(monkeypatch)
    _setup_test_db(monkeypatch)
    _reset_cache()

    with TestClient(main.create_app()) as client:
        token = _create_test_user(client)
        response = client.get(
            "/ask",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 422


def test_ask_requires_auth(monkeypatch):
    monkeypatch.setattr(main, "get_llm_client", lambda: StubLLMClient())
    _mock_qdrant(monkeypatch)
    _setup_test_db(monkeypatch)
    _reset_cache()

    with TestClient(main.create_app()) as client:
        response = client.get("/ask", params={"q": "你好"})

    assert response.status_code == 401
