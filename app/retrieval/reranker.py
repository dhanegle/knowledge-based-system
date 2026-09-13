"""重排器：对向量检索结果按 query-chunk 相关性重新打分。

向量检索（dense search）找的是"相似"的文本块，但相似不等于相关。
重排器用更精细的方法重新评分，把真正相关的提到前面。

接口抽象，两种实现：

- ``KeywordReranker``（默认）：纯本地计算，无外部依赖；
- ``CrossEncoderReranker``：调用 ``/rerank`` 兼容接口的交叉编码器，精度更高，
  由 ``ZHIYUAN_RERANK_BACKEND=model`` 启用，模型配置见 ``.env.example``。

模型重排属可选增强：未配齐或调用失败时自动降级为关键词重排，不阻断问答。
下面这段打分设计仅适用于 KeywordReranker。

## 打分设计

`final = w_vec * norm(vector_score) + w_kw * keyword_hit_rate`

做 min-max 归一化而非直接加权的原因：余弦相似度在真实检索里集中在
0.5~0.8 的窄带，而关键词命中率常落在 0~0.4，量纲虽同为 [0,1] 但分布
差异大。直接相加会让向量分主导，关键词项形同虚设——归一化后两项
才在同一个尺度上竞争。

### ⚠️ 归一化的副作用（需要知道的权衡）

min-max 会把候选集内的向量分差距**拉伸到满量程**：0.90 与 0.60 的
0.30 差距，归一化后变成 1.0 与 0.0 的满差距。这意味着：

- 归一化**增强**了向量项的区分度，但也**放大**了"高相似却离题"的风险；
- 因此关键词权重必须够高（≥0.5）才能纠正这类块；
- 默认 0.7/0.3 是**语义主导**的保守配置，适合通用问答；
  专有名词、术语、编号检索场景建议调高 keyword_weight（如 0.3/0.7）。

权重由 `ZHIYUAN_RERANK_VECTOR_WEIGHT` / `ZHIYUAN_RERANK_KEYWORD_WEIGHT`
控制，可按语料特点调整。
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass

import httpx

from app.config import settings
from app.retrieval.vector_search import RetrievedChunk

logger = logging.getLogger(__name__)


# 高频泛词/疑问词：作为关键词几乎没有区分度（任何文档都可能命中），
# 保留会稀释分母、拉平各块得分，使重排失去意义。
_STOP_TERMS = frozenset({
    # 疑问与指示
    "如何", "怎么", "怎样", "什么", "哪些", "哪个", "是否", "能否", "可以", "需要",
    "这个", "那个", "我们", "你们", "他们", "自己", "一个", "一些",
    # 泛动词/泛名词
    "处理", "使用", "实现", "支持", "包含", "提供", "进行", "完成", "取得",
    "情况", "问题", "方式", "方法", "内容", "结果", "过程", "时候", "地方",
    "系统", "功能", "数据", "信息", "文件", "页面",
    # 单字虚词
    "的", "了", "和", "与", "或", "在", "是", "有", "对", "为", "以", "及",
    "吗", "呢", "吧", "啊", "后", "前", "中", "上", "下",
})


@dataclass
class RerankedChunk:
    """重排后的文本块，带新分数。"""
    text: str
    score: float
    doc_id: str
    filename: str
    page: int
    chunk_index: int
    original_score: float


class RerankerService:
    """重排接口。"""

    async def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_k: int = 5,
    ) -> list[RerankedChunk]:
        """对 chunks 重新打分并取 top_k。"""

    async def aclose(self) -> None:
        """释放资源。无外部连接的实现（如 KeywordReranker）无需覆写。"""
        return


class KeywordReranker(RerankerService):
    """轻量关键词重排器。

    基于 query 中的关键词在 chunk 文本中的命中频率重新打分。
    不需要额外模型，适合开发阶段。生产环境替换为交叉编码器。

    两个关键处理：
    1. **分数归一化**：min-max 把候选集的向量分映射到 [0,1]，
       避免窄带分布（0.5~0.8）下关键词项被压过；
    2. **二元组过滤**：中文 2-gram 会切出「档摄」「入失」这类跨词
       边界的假词，只在候选语料中真实出现过的 2-gram 才计入分母。
    """

    def __init__(
        self,
        vector_weight: float | None = None,
        keyword_weight: float | None = None,
        filter_bigrams: bool | None = None,
    ):
        self._w_vec = (
            vector_weight if vector_weight is not None
            else settings.rerank_vector_weight
        )
        self._w_kw = (
            keyword_weight if keyword_weight is not None
            else settings.rerank_keyword_weight
        )
        self._filter_bigrams = (
            filter_bigrams if filter_bigrams is not None
            else settings.rerank_filter_bigrams
        )
        total = self._w_vec + self._w_kw
        if total <= 0:
            raise ValueError("vector_weight + keyword_weight must be > 0")
        # 归一化为凸组合，保证 final 仍在 [0,1]，便于跨配置比较
        self._w_vec /= total
        self._w_kw /= total

    async def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_k: int = 5,
    ) -> list[RerankedChunk]:
        if not chunks:
            return []

        norm_scores = self._normalize([c.score for c in chunks])
        query_terms = self._extract_terms(query, chunks)

        scored: list[tuple[float, RetrievedChunk, float]] = []
        for chunk, norm in zip(chunks, norm_scores):
            kw_score = self._keyword_score(chunk.text, query_terms)
            final = self._w_vec * norm + self._w_kw * kw_score
            scored.append((final, chunk, kw_score))

        scored.sort(key=lambda x: (-x[0], -x[1].score))

        results = [
            RerankedChunk(
                text=chunk.text,
                score=score,
                doc_id=chunk.doc_id,
                filename=chunk.filename,
                page=chunk.page,
                chunk_index=chunk.chunk_index,
                original_score=chunk.score,
            )
            for score, chunk, _ in scored[:top_k]
        ]
        logger.info(
            "重排: %d → %d 结果 (w_vec=%.2f, w_kw=%.2f, terms=%d)",
            len(chunks), len(results), self._w_vec, self._w_kw, len(query_terms),
        )
        return results

    # ---- 内部方法 ---------------------------------------------------------
    @staticmethod
    def _normalize(scores: list[float]) -> list[float]:
        """min-max 归一化到 [0,1]；全等或只有一个值时返回 1.0。

        返回 1.0 而非 0.0：单候选/分数全同时，向量项应保持中性权重，
        不应把整项抹掉（抹掉会让关键词项独占，反而是种偏差）。
        """
        if not scores:
            return []
        lo, hi = min(scores), max(scores)
        if hi - lo < 1e-12:
            return [1.0] * len(scores)
        return [(s - lo) / (hi - lo) for s in scores]

    def _extract_terms(self, query: str, chunks: list[RetrievedChunk]) -> list[str]:
        """提取查询关键词：英文按单词，中文按 2-gram。

        两级过滤：
        1. **停用词**：疑问词与泛词（「如何」「系统」「处理」）在任何文档里
           都可能命中，保留会拉平候选块得分，直接剔除；
        2. **语料存在性**（`filter_bigrams=True`）：中文 2-gram 会跨词边界
           切出「档摄」「入失」这类假词，候选语料中从未出现过的丢弃。

        第 2 级若把词表清空（候选语料完全未覆盖该主题），回退到未过滤
        列表——宁可带回噪声，也不要让关键词项恒为 0。
        """
        terms: list[str] = []
        terms.extend(w.lower() for w in re.findall(r"[a-zA-Z]{2,}", query))

        chinese = re.findall(r"[\u4e00-\u9fff]", query)
        if len(chinese) == 1:
            terms.append(chinese[0])
        elif len(chinese) >= 2:
            bigrams = ["".join(chinese[i : i + 2]) for i in range(len(chinese) - 1)]
            bigrams = [b for b in bigrams if b not in _STOP_TERMS]
            if self._filter_bigrams and chunks:
                corpus = "\n".join(c.text for c in chunks).lower()
                kept = [b for b in bigrams if b in corpus]
                bigrams = kept or bigrams
            terms.extend(bigrams)

        # 去重但保持顺序，防止重复词拉高分母
        seen: set[str] = set()
        return [t for t in terms if not (t in seen or seen.add(t))]

    @staticmethod
    def _keyword_score(text: str, terms: list[str]) -> float:
        """命中率 = 命中的关键词数 / 关键词总数。"""
        if not terms:
            return 0.0
        text_lower = text.lower()
        hits = sum(1 for term in terms if term in text_lower)
        return hits / len(terms)


def _sigmoid(x: float) -> float:
    """数值稳定的 sigmoid，避免 x 很负时 math.exp 溢出。"""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    z = math.exp(x)
    return z / (1.0 + z)


def _normalize_logits(ranked: list[RerankedChunk]) -> None:
    """分数越界时整体过 sigmoid（原地修改）。

    不同供应商的分数口径不一致：Cohere / Jina / 部分网关返回已归一化的
    [0,1] 相关度，而直接部署的 bge-reranker 常返回原始 logits（可负、可大于 1）。
    后者会让前端显示成「匹配 -8.31」，看着像坏了。

    只在检测到越界时才转换，因此对已归一化的供应商零影响；sigmoid 单调，
    不改变排序结果。
    """
    if not any(c.score < 0.0 or c.score > 1.0 for c in ranked):
        return
    for c in ranked:
        c.score = _sigmoid(c.score)


class CrossEncoderReranker(RerankerService):
    """模型重排：query 与每个候选块成对送入交叉编码器，按重排分排序。

    走业界通用的 ``POST {base_url}/rerank`` 形状（Cohere / Jina /
    SiliconFlow / TEI / Xinference 均实现），换供应商只需改配置：

        请求  {"model": "...", "query": "...", "documents": [...], "top_n": 5}
        响应  {"results": [{"index": 2, "relevance_score": 0.91}, ...]}

    与 KeywordReranker 的本质区别：交叉编码器让 query 与文档**逐对**过一遍
    模型，能建模两者的交互，精度显著高于"向量分 + 关键词命中率"的浅层融合。

    因此这里直接采用模型分作为最终分，向量分只保留在 ``original_score``
    供排查对比，**不做加权混合**——把模型判断和向量分混合反而会稀释它。
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        timeout: float = 30.0,
        http_client: httpx.AsyncClient | None = None,
    ):
        self._http = http_client or httpx.AsyncClient(trust_env=False, timeout=timeout)
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model

    async def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_k: int = 5,
    ) -> list[RerankedChunk]:
        if not chunks:
            return []

        resp = await self._http.post(
            f"{self._base_url}/rerank",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": self._model,
                "query": query,
                "documents": [c.text for c in chunks],
                "top_n": top_k,
            },
        )
        resp.raise_for_status()
        payload = resp.json()
        results = payload.get("results") or []

        ranked: list[RerankedChunk] = []
        for item in results:
            idx = item.get("index")
            # index 越界或类型异常必须跳过：否则会把引用错位到别的文档，
            # 比"少返回几条"严重得多。
            if not isinstance(idx, int) or not 0 <= idx < len(chunks):
                logger.warning("rerank 返回非法 index=%r，已跳过该条", idx)
                continue
            # 兼容 relevance_score（Cohere/Jina/SiliconFlow）与 score（部分网关）
            raw = item.get("relevance_score")
            if raw is None:
                raw = item.get("score")
            chunk = chunks[idx]
            ranked.append(
                RerankedChunk(
                    text=chunk.text,
                    score=float(raw) if raw is not None else 0.0,
                    doc_id=chunk.doc_id,
                    filename=chunk.filename,
                    page=chunk.page,
                    chunk_index=chunk.chunk_index,
                    original_score=chunk.score,
                )
            )

        ranked.sort(key=lambda c: -c.score)
        _normalize_logits(ranked)
        top = ranked[:top_k]
        logger.info(
            "模型重排: %d → %d 结果 (model=%s)", len(chunks), len(top), self._model
        )
        return top

    async def aclose(self) -> None:
        await self._http.aclose()


class FallbackReranker(RerankerService):
    """主重排器抛错时降级到备用实现。

    模型重排是可选增强：上游抖动不应让整条问答链路 500，
    这与项目里缓存 / 鉴权 / 可观测性的降级策略一致。
    降级是逐次生效的——上游恢复后下一次请求自动走主实现。
    """

    def __init__(self, primary: RerankerService, fallback: RerankerService):
        self._primary = primary
        self._fallback = fallback

    async def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_k: int = 5,
    ) -> list[RerankedChunk]:
        if not chunks:
            return []
        try:
            return await self._primary.rerank(query, chunks, top_k=top_k)
        except Exception as exc:
            logger.warning("模型重排失败，本次降级为关键词重排: %s", exc)
            return await self._fallback.rerank(query, chunks, top_k=top_k)

    async def aclose(self) -> None:
        await self._primary.aclose()
        await self._fallback.aclose()


_reranker: RerankerService | None = None


def get_reranker() -> RerankerService:
    """按配置返回重排器。

    - ``ZHIYUAN_RERANK_BACKEND=model`` 且 URL / KEY / MODEL 齐全 → 交叉编码器
      （外面套一层降级包装，失败时退回关键词重排）
    - 其余情况 → KeywordReranker（默认，零外部依赖）
    """
    global _reranker
    if _reranker is not None:
        return _reranker

    if settings.rerank_backend == "model":
        if settings.rerank_model_configured:
            _reranker = FallbackReranker(
                primary=CrossEncoderReranker(
                    base_url=settings.rerank_base_url,
                    api_key=settings.rerank_api_key,
                    model=settings.rerank_model,
                    timeout=settings.rerank_timeout,
                ),
                fallback=KeywordReranker(),
            )
            logger.info(
                "重排器: CrossEncoderReranker (model=%s)", settings.rerank_model
            )
            return _reranker

        logger.warning(
            "rerank_backend=model 但 ZHIYUAN_RERANK_BASE_URL / API_KEY / MODEL "
            "未配齐，已降级为关键词重排"
        )

    _reranker = KeywordReranker()
    return _reranker


async def close_reranker() -> None:
    """关闭并重置重排器（应用关停 / 测试用）。"""
    global _reranker
    if _reranker is not None:
        try:
            await _reranker.aclose()
        except Exception:
            logger.exception("关闭重排器失败")
    _reranker = None
