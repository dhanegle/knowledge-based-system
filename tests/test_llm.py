from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.config import settings
from app.llm.base import (
    OpenAICompatibleLLMClient,
    StubLLMClient,
    _strip_sdk_headers,
    get_llm_client,
)


async def collect(stream: AsyncIterator[str]) -> list[str]:
    return [chunk async for chunk in stream]


@pytest.mark.asyncio
async def test_stub_stream_contains_question():
    chunks = await collect(StubLLMClient().stream("测试问题"))

    assert len(chunks) == 3
    assert "测试问题" in chunks[0]


def test_factory_falls_back_to_stub_for_partial_configuration(monkeypatch):
    monkeypatch.setattr(settings, "llm_base_url", "https://example.test/v1")
    monkeypatch.setattr(settings, "llm_api_key", "")
    monkeypatch.setattr(settings, "llm_model", "test-model")

    assert isinstance(get_llm_client(), StubLLMClient)


@pytest.mark.asyncio
async def test_openai_stream_builds_system_context_messages():
    client = OpenAICompatibleLLMClient(
        base_url="https://example.test/v1",
        api_key="test-key",
        model="test-model",
    )

    chunks = [
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="你好"))]),
        SimpleNamespace(choices=[]),
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="世界"))]),
    ]

    class FakeStream:
        def __init__(self, values):
            self.values = iter(values)

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self.values)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    create = AsyncMock(return_value=FakeStream(chunks))
    client._client.chat.completions.create = create

    try:
        result = await collect(
            client.stream(
                "问题",
                system_prompt="你是助手",
                context="文档片段",
            )
        )
    finally:
        await client.aclose()

    assert result == ["你好", "世界"]
    assert create.await_args.kwargs["messages"] == [
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "参考信息：\n文档片段\n\n问题：问题"},
    ]
    assert create.await_args.kwargs["stream"] is True


@pytest.mark.asyncio
async def test_strip_sdk_headers_replaces_user_agent():
    request = httpx.Request(
        "GET",
        "https://example.test",
        headers={"X-Stainless-Lang": "python", "User-Agent": "sdk"},
    )

    await _strip_sdk_headers(request)

    assert "x-stainless-lang" not in request.headers
    assert request.headers["user-agent"] == "zhiyuan/0.1"
