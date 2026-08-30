"""Embedding 服务测试。"""

import pytest

from app.embedding.base import StubEmbeddingService


@pytest.mark.asyncio
async def test_stub_embed_returns_correct_dimension():
    service = StubEmbeddingService(dim=1024)
    vectors = await service.embed(["测试文本"])

    assert len(vectors) == 1
    assert len(vectors[0]) == 1024


@pytest.mark.asyncio
async def test_stub_embed_one_matches_batch():
    service = StubEmbeddingService(dim=128)
    batch_result = await service.embed(["hello", "world"])
    single_result = await service.embed_one("hello")

    assert batch_result[0] == single_result


@pytest.mark.asyncio
async def test_stub_same_text_produces_same_vector():
    service = StubEmbeddingService(dim=64)
    v1 = await service.embed_one("相同文本")
    v2 = await service.embed_one("相同文本")

    assert v1 == v2


@pytest.mark.asyncio
async def test_stub_different_text_produces_different_vector():
    service = StubEmbeddingService(dim=64)
    v1 = await service.embed_one("文本A")
    v2 = await service.embed_one("文本B")

    assert v1 != v2


def test_stub_dimension_property():
    service = StubEmbeddingService(dim=256)
    assert service.dimension == 256


async def test_factory_returns_langchain_backend_when_configured(monkeypatch):
    import app.embedding.base as emb_mod
    from app.config import settings
    from app.embedding.base import get_embedding_service
    from app.embedding.langchain_service import LangChainEmbeddingService

    monkeypatch.setattr(settings, "embedding_base_url", "https://example.test/v1")
    monkeypatch.setattr(settings, "embedding_api_key", "test-key")
    monkeypatch.setattr(settings, "embedding_model", "test-model")
    monkeypatch.setattr(settings, "embedding_backend", "langchain")
    monkeypatch.setattr(emb_mod, "_embedding_service", None)

    service = get_embedding_service()
    try:
        assert isinstance(service, LangChainEmbeddingService)
        assert service.dimension == settings.embedding_dim
    finally:
        await service.close()


async def test_langchain_service_delegates_embed_and_query(monkeypatch):
    from langchain_openai import OpenAIEmbeddings

    from app.embedding.langchain_service import LangChainEmbeddingService

    service = LangChainEmbeddingService(
        base_url="https://example.test/v1",
        api_key="test-key",
        model="test-model",
        dim=768,
    )
    calls = []

    async def fake_aembed_documents(texts):
        calls.append(("documents", texts))
        return [[0.1] * 768, [0.2] * 768]

    async def fake_aembed_query(text):
        calls.append(("query", text))
        return [0.3] * 768

    monkeypatch.setattr(
        OpenAIEmbeddings, "aembed_documents", staticmethod(fake_aembed_documents)
    )
    monkeypatch.setattr(
        OpenAIEmbeddings, "aembed_query", staticmethod(fake_aembed_query)
    )

    try:
        batch = await service.embed(["文本A", "文本B"])
        single = await service.embed_one("问题")
    finally:
        await service.close()

    assert len(batch) == 2
    assert len(batch[0]) == 768
    assert len(single) == 768
    assert calls == [("documents", ["文本A", "文本B"]), ("query", "问题")]
