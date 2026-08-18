"""鉴权模块测试：JWT、密码哈希、注册/登录流程。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main
from app.auth.jwt import create_access_token, decode_access_token
from app.auth.password import hash_password, verify_password
from app.config import settings
from app.llm.base import StubLLMClient


def _mock_infra(monkeypatch):
    """Mock Qdrant + embedding for test isolation."""
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

    # Use in-memory SQLite, unique per test via random suffix
    import uuid as _uuid
    db_id = _uuid.uuid4().hex
    monkeypatch.setattr(
        settings, "database_url", f"sqlite+aiosqlite:///file:{db_id}?mode=memory&cache=shared"
    )
    # Reset engine singleton so new URL takes effect
    import app.storage.session as session_mod
    session_mod._engine = None

    return fake


def test_jwt_round_trip():
    token = create_access_token({"sub": "alice"})
    payload = decode_access_token(token)
    assert payload["sub"] == "alice"
    assert "exp" in payload


def test_password_hash_and_verify():
    h = hash_password("secret123")
    assert h != "secret123"
    assert verify_password("secret123", h)
    assert not verify_password("wrong", h)


def test_register_and_login(monkeypatch):
    monkeypatch.setattr(main, "get_llm_client", lambda: StubLLMClient())
    _mock_infra(monkeypatch)

    with TestClient(main.create_app()) as client:
        # Register
        resp = client.post(
            "/auth/register",
            json={
                "username": "testuser",
                "email": "test@example.com",
                "password": "password123",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["token_type"] == "bearer"
        assert data["username"] == "testuser"
        assert "access_token" in data

        # Login with correct password
        resp = client.post(
            "/auth/login",
            json={"username": "testuser", "password": "password123"},
        )
        assert resp.status_code == 200
        assert resp.json()["access_token"]

        # Login with wrong password
        resp = client.post(
            "/auth/login",
            json={"username": "testuser", "password": "wrong"},
        )
        assert resp.status_code == 401


def test_register_duplicate_username(monkeypatch):
    monkeypatch.setattr(main, "get_llm_client", lambda: StubLLMClient())
    _mock_infra(monkeypatch)

    with TestClient(main.create_app()) as client:
        payload = {
            "username": "dupuser",
            "email": "dup1@example.com",
            "password": "password123",
        }
        resp = client.post("/auth/register", json=payload)
        assert resp.status_code == 201

        # Same username, different email
        payload["email"] = "dup2@example.com"
        resp = client.post("/auth/register", json=payload)
        assert resp.status_code == 409


def test_me_endpoint_requires_auth(monkeypatch):
    monkeypatch.setattr(main, "get_llm_client", lambda: StubLLMClient())
    _mock_infra(monkeypatch)

    with TestClient(main.create_app()) as client:
        # No token → 401
        resp = client.get("/auth/me")
        assert resp.status_code == 401

        # Register and get token
        resp = client.post(
            "/auth/register",
            json={
                "username": "meuser",
                "email": "me@example.com",
                "password": "password123",
            },
        )
        token = resp.json()["access_token"]

        # With token → 200
        resp = client.get(
            "/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        assert resp.json()["username"] == "meuser"


def test_refresh_token(monkeypatch):
    monkeypatch.setattr(main, "get_llm_client", lambda: StubLLMClient())
    _mock_infra(monkeypatch)

    with TestClient(main.create_app()) as client:
        resp = client.post(
            "/auth/register",
            json={
                "username": "refreshuser",
                "email": "refresh@example.com",
                "password": "password123",
            },
        )
        token = resp.json()["access_token"]

        resp = client.post(
            "/auth/refresh", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        assert resp.json()["access_token"]
