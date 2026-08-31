"""RAGService 双路径测试：原生 stream 与 LangChain LCEL。"""

from typing import ClassVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.llm.base import StubLLMClient
from app.rag.prompt_builder import SYSTEM_PROMPT
from app.rag.rag_service import RAGService
from app.retrieval.reranker import RerankedChunk, RerankerService
from app.retrieval.vector_search import RetrievedChunk


def make_chunks():
    return [
        RetrievedChunk(
            text="知源是知识库问答系统", score=0.9, doc_id="d1",
            filename="intro.md", page=1, chunk_index=0,
        ),
        RetrievedChunk(
            text="部署用 docker compose", score=0.6, doc_id="d2",
            filename="deploy.md", page=2, chunk_index=1,
        ),
    ]


class FakeSearcher:
    def __init__(self, chunks):
        self._chunks = chunks

    async def search(self, query, doc_ids=None):
        return self._chunks


class FakeReranker(RerankerService):
    async def rerank(self, query, chunks, top_k=5):
        return [
            RerankedChunk(
                text=c.text, score=c.score, doc_id=c.doc_id,
                filename=c.filename, page=c.page, chunk_index=c.chunk_index,
                original_score=c.score,
            )
            for c in chunks[:top_k]
        ]


class RecordingChatModel(BaseChatModel):
    received: ClassVar[list] = []

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        type(self).received.append(list(messages))
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="知识库回答"))])

    @property
    def _llm_type(self):
        return "recording"


async def test_lcel_path_streams_and_returns_sources():
    RecordingChatModel.received = []
    rag = RAGService(
        llm_client=StubLLMClient(),
        searcher=FakeSearcher(make_chunks()),
        reranker=FakeReranker(),
        chat_model=RecordingChatModel(),
    )

    stream, sources = await rag.ask("什么是知源")
    tokens = [t async for t in stream]

    assert tokens == ["知识库回答"]
    assert len(sources) == 2
    assert sources[0]["filename"] == "intro.md"
    assert sources[0]["score"] == 0.9
    assert "text_preview" in sources[0]
    assert len(RecordingChatModel.received) == 1
    sent = RecordingChatModel.received[0]
    assert [m.type for m in sent] == ["system", "human"]
    assert sent[0].content == SYSTEM_PROMPT
    assert "参考信息" in sent[1].content
    assert "什么是知源" in sent[1].content


async def test_native_path_streams_and_returns_sources():
    class FakeNativeClient:
        async def stream(self, question, *, system_prompt="", context=""):
            assert system_prompt == SYSTEM_PROMPT
            assert "参考信息" in question
            yield "原生"
            yield "回答"

        async def aclose(self):
            pass

    rag = RAGService(
        llm_client=FakeNativeClient(),
        searcher=FakeSearcher(make_chunks()),
        reranker=FakeReranker(),
    )

    stream, sources = await rag.ask("什么是知源")
    tokens = [t async for t in stream]

    assert tokens == ["原生", "回答"]
    assert len(sources) == 2


async def test_lcel_path_without_context_falls_back_to_plain_question():
    RecordingChatModel.received = []
    rag = RAGService(
        llm_client=StubLLMClient(),
        searcher=FakeSearcher([]),
        reranker=FakeReranker(),
        chat_model=RecordingChatModel(),
    )

    stream, sources = await rag.ask("天气如何")
    tokens = [t async for t in stream]

    assert tokens == ["知识库回答"]
    assert sources == []
    sent = RecordingChatModel.received[0]
    assert sent[1].content == "天气如何"
