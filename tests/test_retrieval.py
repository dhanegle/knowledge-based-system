"""ZhiyuanRetriever（LangChain BaseRetriever 适配）与重排器测试。"""

import json

import httpx

from app.config import settings
from app.retrieval.langchain_retriever import ZhiyuanRetriever
from app.retrieval.reranker import (
    CrossEncoderReranker,
    FallbackReranker,
    KeywordReranker,
    _sigmoid,
    get_reranker,
)
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


# ---------------------------------------------------------------------------
# KeywordReranker
# ---------------------------------------------------------------------------
def _chunk(text: str, score: float, idx: int = 0) -> RetrievedChunk:
    return RetrievedChunk(
        text=text, score=score, doc_id="d1",
        filename="f.md", page=1, chunk_index=idx,
    )


async def test_rerank_promotes_keyword_matching_chunk():
    """关键词命中率高的块应被提到前面。

    注意：min-max 会把候选集内的向量分差距拉伸到满量程，
    因此关键词权重需要足够高才能纠正"高相似但离题"的块。
    这里用 0.3/0.7（偏关键词）验证纠偏能力；默认 0.7/0.3 用于
    语义为主的通用场景——两者是不同权衡，不是谁对谁错。
    """
    reranker = KeywordReranker(vector_weight=0.3, keyword_weight=0.7)
    chunks = [
        _chunk("这段文本与查询主题无关，只是向量相似度偏高。", 0.90, 0),
        _chunk("文档摄入失败后可以重新摄入，系统会重建索引。", 0.60, 1),
    ]

    result = await reranker.rerank("文档摄入失败后重新处理", chunks, top_k=2)

    assert result[0].chunk_index == 1
    assert result[0].original_score == 0.60


async def test_rerank_vector_dominant_by_default():
    """默认权重（0.7 向量 / 0.3 关键词）下向量分主导，保持语义优先。"""
    reranker = KeywordReranker(vector_weight=0.7, keyword_weight=0.3)
    chunks = [
        _chunk("这段文本与查询主题无关，只是向量相似度偏高。", 0.90, 0),
        _chunk("文档摄入失败后可以重新摄入，系统会重建索引。", 0.60, 1),
    ]

    result = await reranker.rerank("文档摄入失败后重新处理", chunks, top_k=2)

    assert result[0].chunk_index == 0


async def test_rerank_empty_input_returns_empty():
    reranker = KeywordReranker()
    assert await reranker.rerank("任意问题", [], top_k=5) == []


async def test_rerank_respects_top_k():
    reranker = KeywordReranker()
    chunks = [_chunk(f"文本{i}", 0.5 + i * 0.01, i) for i in range(10)]

    result = await reranker.rerank("文本", chunks, top_k=3)

    assert len(result) == 3


async def test_rerank_weights_are_normalized():
    """权重先归一化为凸组合，保证 final 分数仍在 [0,1]。"""
    reranker = KeywordReranker(vector_weight=7.0, keyword_weight=3.0)

    assert abs(reranker._w_vec - 0.7) < 1e-9
    assert abs(reranker._w_kw - 0.3) < 1e-9


async def test_rerank_rejects_all_zero_weights():
    import pytest

    with pytest.raises(ValueError):
        KeywordReranker(vector_weight=0.0, keyword_weight=0.0)


def test_normalize_handles_uniform_scores():
    """分数全同时返回 1.0，保持向量项的中性权重而非抹掉。"""
    assert KeywordReranker._normalize([0.7, 0.7, 0.7]) == [1.0, 1.0, 1.0]


def test_normalize_maps_to_unit_range():
    norm = KeywordReranker._normalize([0.5, 0.6, 0.8])

    assert norm[0] == 0.0
    assert norm[-1] == 1.0
    assert 0.0 < norm[1] < 1.0


def test_extract_terms_drops_stopwords():
    """疑问词与泛词不应成为关键词。"""
    reranker = KeywordReranker(filter_bigrams=False)

    terms = reranker._extract_terms("系统如何处理数据", [])

    assert "如何" not in terms
    assert "处理" not in terms
    assert "系统" not in terms


def test_extract_terms_filters_fake_bigrams():
    """跨词边界的假二元组在候选语料中不存在时被丢弃。"""
    reranker = KeywordReranker(filter_bigrams=True)
    chunks = [_chunk("文档摄入失败的处理流程说明。", 0.6)]

    terms = reranker._extract_terms("文档摄入失败", chunks)

    assert "文档" in terms
    assert "摄入" in terms
    assert "失败" in terms


def test_extract_terms_keeps_all_when_corpus_misses_topic():
    """候选语料完全未覆盖主题时，回退到未过滤词表而非清空。"""
    reranker = KeywordReranker(filter_bigrams=True)
    chunks = [_chunk("完全不相关的一段文本。", 0.6)]

    terms = reranker._extract_terms("量子纠缠退相干", chunks)

    assert terms  # 不为空


# ---------------------------------------------------------------------------
# CrossEncoderReranker（模型重排）与降级包装
# ---------------------------------------------------------------------------
def _mock_http(handler):
    """构造不触网的 httpx 客户端。"""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)


async def test_model_reranker_orders_by_relevance_score():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 2, "relevance_score": 0.91},
                    {"index": 0, "relevance_score": 0.55},
                ]
            },
        )

    reranker = CrossEncoderReranker(
        "https://rerank.test/v1",
        "key",
        "BAAI/bge-reranker-v2-m3",
        http_client=_mock_http(handler),
    )
    chunks = [
        _chunk("文本甲", 0.70, 0),
        _chunk("文本乙", 0.60, 1),
        _chunk("文本丙", 0.50, 2),
    ]

    result = await reranker.rerank("查询词", chunks, top_k=2)

    # 请求形状：换供应商只改配置，这里锁定契约
    assert seen["model"] == "BAAI/bge-reranker-v2-m3"
    assert seen["query"] == "查询词"
    assert seen["documents"] == ["文本甲", "文本乙", "文本丙"]
    assert seen["top_n"] == 2

    # 按模型分重排，且保留原向量分供对比
    assert [c.chunk_index for c in result] == [2, 0]
    assert result[0].score == 0.91
    assert result[0].original_score == 0.50

    await reranker.aclose()


async def test_model_reranker_accepts_plain_score_field():
    """部分网关用 score 而非 relevance_score，两者都要能解析。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [{"index": 1, "score": 0.8}]})

    reranker = CrossEncoderReranker(
        "https://rerank.test/v1", "key", "m", http_client=_mock_http(handler)
    )

    result = await reranker.rerank("q", [_chunk("甲", 0.6, 0), _chunk("乙", 0.4, 1)], top_k=1)

    assert len(result) == 1
    assert result[0].chunk_index == 1
    assert result[0].score == 0.8
    await reranker.aclose()


async def test_model_reranker_skips_out_of_range_index():
    """越界 index 必须跳过，否则引用会错位到别的文档。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 99, "relevance_score": 0.99},
                    {"index": 0, "relevance_score": 0.40},
                ]
            },
        )

    reranker = CrossEncoderReranker(
        "https://rerank.test/v1", "key", "m", http_client=_mock_http(handler)
    )

    result = await reranker.rerank("q", [_chunk("甲", 0.6, 0)], top_k=5)

    assert [c.chunk_index for c in result] == [0]
    await reranker.aclose()


async def test_model_reranker_empty_chunks_makes_no_request():
    """候选为空时不应发起 HTTP 请求。"""
    called = []

    def handler(request: httpx.Request) -> httpx.Response:
        called.append(request)
        return httpx.Response(200, json={"results": []})

    reranker = CrossEncoderReranker(
        "https://rerank.test/v1", "key", "m", http_client=_mock_http(handler)
    )

    assert await reranker.rerank("q", [], top_k=5) == []
    assert called == []
    await reranker.aclose()


async def test_fallback_reranker_degrades_on_primary_failure():
    """主重排器抛错时降级，而不是让查询失败。"""

    class Boom:
        async def rerank(self, query, chunks, top_k=5):
            raise RuntimeError("upstream 502")

        async def aclose(self):
            pass

    wrapper = FallbackReranker(primary=Boom(), fallback=KeywordReranker())
    chunks = [_chunk("文档摄入失败的处理流程说明。", 0.60, 0)]

    result = await wrapper.rerank("文档摄入失败", chunks, top_k=1)

    assert len(result) == 1
    assert result[0].chunk_index == 0
    await wrapper.aclose()


def test_get_reranker_defaults_to_keyword(monkeypatch):
    import app.retrieval.reranker as reranker_mod

    monkeypatch.setattr(reranker_mod, "_reranker", None)
    monkeypatch.setattr(settings, "rerank_backend", "keyword")

    assert isinstance(get_reranker(), KeywordReranker)


def test_get_reranker_falls_back_when_model_unconfigured(monkeypatch):
    """选了 model 但配置没填齐，应降级而不是崩在启动上。"""
    import app.retrieval.reranker as reranker_mod

    monkeypatch.setattr(reranker_mod, "_reranker", None)
    monkeypatch.setattr(settings, "rerank_backend", "model")
    monkeypatch.setattr(settings, "rerank_base_url", "")
    monkeypatch.setattr(settings, "rerank_api_key", "")
    monkeypatch.setattr(settings, "rerank_model", "")

    assert isinstance(get_reranker(), KeywordReranker)


def test_get_reranker_builds_model_reranker_when_configured(monkeypatch):
    import app.retrieval.reranker as reranker_mod

    monkeypatch.setattr(reranker_mod, "_reranker", None)
    monkeypatch.setattr(settings, "rerank_backend", "model")
    monkeypatch.setattr(settings, "rerank_base_url", "https://rerank.test/v1")
    monkeypatch.setattr(settings, "rerank_api_key", "key")
    monkeypatch.setattr(settings, "rerank_model", "BAAI/bge-reranker-v2-m3")

    reranker = get_reranker()

    assert isinstance(reranker, FallbackReranker)
    assert isinstance(reranker._primary, CrossEncoderReranker)
    assert isinstance(reranker._fallback, KeywordReranker)

    # 清理单例，避免污染后续测试
    reranker_mod._reranker = None


# ---------------------------------------------------------------------------
# 分数口径兼容：logits vs 已归一化
# ---------------------------------------------------------------------------
async def test_model_reranker_normalizes_logit_scores():
    """供应商返回原始 logits 时应映射到 [0,1]。

    直接部署的 bge-reranker 常返回 logits（可负），不处理会让前端
    显示成「匹配 -8.31」，看着像坏了。
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 0, "relevance_score": 8.0},
                    {"index": 1, "relevance_score": -8.0},
                ]
            },
        )

    reranker = CrossEncoderReranker(
        "https://rerank.test/v1", "key", "m", http_client=_mock_http(handler)
    )

    result = await reranker.rerank(
        "q", [_chunk("甲", 0.6, 0), _chunk("乙", 0.5, 1)], top_k=2
    )

    assert all(0.0 <= c.score <= 1.0 for c in result)
    assert result[0].score > 0.9  # sigmoid(8)
    assert result[1].score < 0.1  # sigmoid(-8)
    await reranker.aclose()


async def test_model_reranker_keeps_normalized_scores_untouched():
    """已是 [0,1] 的供应商不应被 sigmoid 二次变换（那会破坏原始相关度）。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"results": [{"index": 0, "relevance_score": 0.9564176201820374}]}
        )

    reranker = CrossEncoderReranker(
        "https://rerank.test/v1", "key", "m", http_client=_mock_http(handler)
    )

    result = await reranker.rerank("q", [_chunk("甲", 0.6, 0)], top_k=1)

    assert result[0].score == 0.9564176201820374
    await reranker.aclose()


def test_sigmoid_survives_extreme_values():
    """数值稳定性：极大/极小输入不得抛 OverflowError。"""
    assert _sigmoid(0.0) == 0.5
    assert _sigmoid(1e6) == 1.0
    assert _sigmoid(-1e6) == 0.0
