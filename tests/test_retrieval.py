"""ZhiyuanRetriever（LangChain BaseRetriever 适配）测试。"""

from app.retrieval.langchain_retriever import ZhiyuanRetriever
from app.retrieval.vector_search import RetrievedChunk


class FakeSearcher:
    def __init__(self, chunks):
        self._chunks = chunks
        self.calls = []

    async def search(self, query, doc_ids=None):
        self.calls.append((query, doc_ids))
        return self._chunks


async def test_retriever_maps_chunks_to_documents():
    searcher = FakeSearcher([
        RetrievedChunk(
            text="知源是知识库系统", score=0.87, doc_id="d1",
            filename="intro.md", page=3, chunk_index=0,
        ),
    ])
    retriever = ZhiyuanRetriever(searcher=searcher, doc_ids=["d1"])

    docs = await retriever.ainvoke("什么是知源")

    assert len(docs) == 1
    assert docs[0].page_content == "知源是知识库系统"
    assert docs[0].metadata == {
        "doc_id": "d1",
        "filename": "intro.md",
        "page": 3,
        "chunk_index": 0,
        "score": 0.87,
    }
    assert searcher.calls == [("什么是知源", ["d1"])]


async def test_retriever_passes_none_doc_ids_by_default():
    searcher = FakeSearcher([])
    retriever = ZhiyuanRetriever(searcher=searcher)

    docs = await retriever.ainvoke("任意问题")

    assert docs == []
    assert searcher.calls == [("任意问题", None)]
