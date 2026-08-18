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
