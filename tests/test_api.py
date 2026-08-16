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


def test_health_requires_all_llm_settings(monkeypatch):
    monkeypatch.setattr(main, "get_llm_client", lambda: StubLLMClient())
    monkeypatch.setattr(settings, "llm_base_url", "")
    monkeypatch.setattr(settings, "llm_api_key", "configured")
    monkeypatch.setattr(settings, "llm_model", "")

    with TestClient(main.create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["llm_configured"] is False


def test_health_reports_configured_when_all_llm_settings_exist(monkeypatch):
    monkeypatch.setattr(main, "get_llm_client", lambda: StubLLMClient())
    monkeypatch.setattr(settings, "llm_base_url", "https://example.test/v1")
    monkeypatch.setattr(settings, "llm_api_key", "configured")
    monkeypatch.setattr(settings, "llm_model", "test-model")

    with TestClient(main.create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["llm_configured"] is True


def test_ask_streams_tokens_and_closes_shared_client(monkeypatch):
    llm = RecordingLLMClient()
    monkeypatch.setattr(main, "get_llm_client", lambda: llm)

    with TestClient(main.create_app()) as client:
        response = client.get("/ask", params={"q": "你好"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert 'event: token\r\ndata: {"text": "第一段"}' in response.text
    assert 'event: token\r\ndata: {"text": "第二段"}' in response.text
    assert 'event: done\r\ndata: {"ok": true}' in response.text
    assert llm.closed is True


def test_ask_emits_error_event_without_upstream_details(monkeypatch):
    monkeypatch.setattr(main, "get_llm_client", lambda: FailingLLMClient())

    with TestClient(main.create_app()) as client:
        response = client.get("/ask", params={"q": "hello"})

    assert response.status_code == 200
    assert 'event: error\r\ndata: {"ok": false, "error": "LLM request failed"}' in response.text
    assert "upstream details must not reach" not in response.text
    assert "event: done" not in response.text


def test_ask_requires_question(monkeypatch):
    monkeypatch.setattr(main, "get_llm_client", lambda: StubLLMClient())

    with TestClient(main.create_app()) as client:
        response = client.get("/ask")

    assert response.status_code == 422
