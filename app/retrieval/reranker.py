"""重排器：对向量检索结果按 query-chunk 相关性重新打分。

向量检索（dense search）找的是"相似"的文本块，但相似不等于相关。
重排器用更精细的方法（交叉编码器）重新评分，把真正相关的提到前面。

接口抽象，当前实现是轻量关键词重排；未来可替换为 bge-reranker 交叉编码器。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.retrieval.vector_search import RetrievedChunk

logger = logging.getLogger(__name__)


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


class KeywordReranker(RerankerService):
    """轻量关键词重排器。

    基于 query 中的关键词在 chunk 文本中的命中频率重新打分。
    不需要额外模型，适合开发阶段。生产环境替换为交叉编码器。
    """

    async def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_k: int = 5,
    ) -> list[RerankedChunk]:
        query_terms = self._extract_terms(query)
        scored: list[tuple[float, RetrievedChunk]] = []

        for chunk in chunks:
            rerank_score = self._score(chunk.text, query_terms, chunk.score)
            scored.append((rerank_score, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)

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
            for score, chunk in scored[:top_k]
        ]
        logger.info("重排: %d → %d 结果", len(chunks), len(results))
        return results

    def _extract_terms(self, query: str) -> list[str]:
        """提取查询中的关键词（中文按字符 n-gram，英文按单词）。"""
        terms: list[str] = []
        # 英文单词
        english_words = re.findall(r"[a-zA-Z]{2,}", query)
        terms.extend(w.lower() for w in english_words)
        # 中文 2-gram（findall 返回列表，需 join 成字符串）
        chinese_chars = re.findall(r"[一-鿿]", query)
        for i in range(len(chinese_chars) - 1):
            terms.append("".join(chinese_chars[i : i + 2]))
        if len(chinese_chars) == 1:
            terms.append(chinese_chars[0])
        return terms

    def _score(self, text: str, terms: list[str], original_score: float) -> float:
        """综合原始向量分数和关键词命中频率。"""
        if not terms:
            return original_score
        text_lower = text.lower()
        hits = sum(1 for term in terms if term in text_lower)
        keyword_score = hits / len(terms)
        # 70% 向量分数 + 30% 关键词匹配
        return 0.7 * original_score + 0.3 * keyword_score


_reranker: RerankerService | None = None


def get_reranker() -> RerankerService:
    global _reranker
    if _reranker is None:
        _reranker = KeywordReranker()
    return _reranker
