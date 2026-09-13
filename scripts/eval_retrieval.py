"""知源检索评测：重排效果对比（纯向量 / 旧版直接加权 / 新版归一化+二元组过滤）。

零外部依赖、零 API 成本：
- 不调用真实 embedding API 与 Qdrant，而是用人工构造的候选块
  （模拟向量检索 top-K 的召回结果，含相关与干扰项）作为输入。
- 对比三种排序策略的排名质量，指标：HitRate@1 / @3 / @5、MRR。

用法：
    python scripts/eval_retrieval.py
"""
from __future__ import annotations

import asyncio
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.retrieval.reranker import KeywordReranker
from app.retrieval.vector_search import RetrievedChunk


# ---------------------------------------------------------------------------
# 评测集：每个 case = 1 个 query + 候选块（related=True 为正确答案）
# 向量分数刻意设置成"正确答案分数不占优"，用于检验重排的纠偏能力。
# ---------------------------------------------------------------------------
@dataclass
class Candidate:
    text: str
    score: float          # 模拟的向量相似度分数
    related: bool = False  # 是否应被判为相关（gold）


@dataclass
class Case:
    query: str
    candidates: list[Candidate]


CASES: list[Case] = [
    Case(
        query="文档摄入失败后如何重新处理",
        candidates=[
            Candidate("在线问答使用 SSE 流式返回生成结果，前端逐块渲染。", 0.82),
            Candidate("文档摄入管线的状态机包含 parsing/chunking/embedding 阶段，"
                      "失败会标记为 failed，支持失败重摄入与增量更新。", 0.62, related=True),
            Candidate("Qdrant 的集合维度必须与 embedding 输出维度一致。", 0.71),
            Candidate("用户权限分为 owner/admin/user 三级。", 0.68),
            Candidate("摄入失败的文档可以在管理后台点击重新摄入，系统会重新解析并建立索引。", 0.55),
        ],
    ),
    Case(
        query="如何保证同一文件不会重复入库",
        candidates=[
            Candidate("查询缓存按用户隔离，避免不同用户看到彼此的对话历史。", 0.79),
            Candidate("文档以内容 SHA-256 做去重，相同内容即使文件名不同也只入库一次。", 0.58, related=True),
            Candidate("Redis 不可用时会降级为直连数据库查询。", 0.74),
            Candidate("管理员可以删除文档，同时清理向量库中的对应向量。", 0.66),
        ],
    ),
    Case(
        query="系统里 Redis 挂了会怎样",
        candidates=[
            Candidate("缓存与可观测组件不可用时逐级降级，主链路不中断。"
                      "Redis 挂掉则跳过缓存直接查询数据库与向量库。", 0.61, related=True),
            Candidate("Langfuse 用于记录链路追踪，便于排查检索与生成问题。", 0.77),
            Candidate("文档分块大小为 500 字符，重叠 50 字符。", 0.72),
            Candidate("前端使用 Vue 3 实现对话界面。", 0.69),
        ],
    ),
    Case(
        query="embedding 维度配置在哪里",
        candidates=[
            Candidate("配置文件里 ZHIYUAN_EMBEDDING_DIM 指定向量维度，默认 768 维。", 0.57, related=True),
            Candidate("关键词重排会综合原始向量分数与关键词命中频率。", 0.81),
            Candidate("订单状态机使用 CAS 乐观锁保证并发正确性。", 0.75),
            Candidate("Docker Compose 可以一键启动整套服务。", 0.70),
        ],
    ),
    Case(
        query="多个格式的文档都能解析吗",
        candidates=[
            Candidate("支持 PDF、Word、PPT、Excel、Markdown 与源码等多种格式解析。", 0.59, related=True),
            Candidate("SSE 适合单向的流式输出场景。", 0.80),
            Candidate("角色权限校验放在依赖注入层统一处理。", 0.73),
            Candidate("重排后的结果只取 top-5 注入到生成上下文。", 0.67),
        ],
    ),
    Case(
        query="回答引用了哪些来源",
        candidates=[
            Candidate("生成接口会返回引用来源列表，包含文件名、页码与文本块序号。", 0.60, related=True),
            Candidate("Qdrant 的搜索支持按 doc_ids 过滤。", 0.78),
            Candidate("ruff 用于代码检查，target-version 为 py312。", 0.71),
            Candidate("bcrypt 用于密码哈希。", 0.65),
        ],
    ),
    Case(
        query="上传的文件大小有限制吗",
        candidates=[
            Candidate("单文件上传上限为 50MB，接口按块读取以免耗尽内存。", 0.58, related=True),
            Candidate("JWT 过期时间为 24 小时。", 0.79),
            Candidate("日志用 structlog 输出结构化字段。", 0.74),
            Candidate("重排接口抽象为 RerankerService。", 0.66),
        ],
    ),
    Case(
        query="怎么知道检索结果好不好",
        candidates=[
            Candidate("用带标注的评测集计算 HitRate 与 MRR，做重排前后 A/B 对比。", 0.56, related=True),
            Candidate("Qdrant 使用 HNSW 索引加速近邻搜索。", 0.80),
            Candidate("前端通过 SSE 接收流式 token。", 0.72),
            Candidate("密码使用 bcrypt 哈希后存储。", 0.68),
        ],
    ),
]


def _old_terms(query: str) -> list[str]:
    """旧版关键词抽取：包含全部 2-gram，不做语料过滤。"""
    terms = [w.lower() for w in re.findall(r"[a-zA-Z]{2,}", query)]
    chinese = re.findall(r"[\u4e00-\u9fff]", query)
    if len(chinese) == 1:
        terms.append(chinese[0])
    for i in range(len(chinese) - 1):
        terms.append("".join(chinese[i : i + 2]))
    return terms


def _old_keyword_score(text: str, terms: list[str]) -> float:
    if not terms:
        return 0.0
    text_lower = text.lower()
    return sum(1 for t in terms if t in text_lower) / len(terms)


def _to_chunks(cands: list[Candidate], case_idx: int) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            text=c.text, score=c.score, doc_id=f"doc{case_idx}",
            filename=f"doc{case_idx}.md", page=1, chunk_index=i,
        )
        for i, c in enumerate(cands)
    ]


def _rank_of_gold(items: list, gold_texts: set[str], key) -> int:
    """返回第一个命中 gold 的排名（1-based）；未命中返回 0。"""
    for rank, it in enumerate(items, 1):
        if key(it) in gold_texts:
            return rank
    return 0


def _metrics(ranks: list[int]) -> dict:
    n = len(ranks)
    return {
        "HitRate@1": sum(1 for r in ranks if r == 1) / n,
        "HitRate@3": sum(1 for r in ranks if 1 <= r <= 3) / n,
        "HitRate@5": sum(1 for r in ranks if 1 <= r <= 5) / n,
        "MRR": sum((1.0 / r if r else 0.0) for r in ranks) / n,
    }


async def main() -> None:
    # 三种策略：
    #   A 纯向量（基线）
    #   B 旧版：直接加权——不做分数归一化、不过滤无意义二元组
    #   C 新版：min-max 归一化 + 候选语料二元组过滤
    old_reranker = KeywordReranker(filter_bigrams=False)
    new_reranker = KeywordReranker(filter_bigrams=True)

    base_ranks: list[int] = []
    old_ranks: list[int] = []
    new_ranks: list[int] = []
    details = []

    for i, case in enumerate(CASES):
        chunks = _to_chunks(case.candidates, i)
        gold_texts = {c.text for c in case.candidates if c.related}

        # A 纯向量
        base_sorted = sorted(chunks, key=lambda c: c.score, reverse=True)
        base_rank = _rank_of_gold(base_sorted, gold_texts, lambda c: c.text)
        base_ranks.append(base_rank)

        # B 旧版：原始向量分直接 + 全部 2-gram 命中率（不经归一化）
        terms = _old_terms(case.query)
        old_sorted = sorted(
            chunks,
            key=lambda c: -(0.7 * c.score + 0.3 * _old_keyword_score(c.text, terms)),
        )
        old_rank = _rank_of_gold(old_sorted, gold_texts, lambda c: c.text)
        old_ranks.append(old_rank)

        # C 新版
        reranked = await old_reranker.rerank(case.query, chunks, top_k=len(chunks))
        rerank_old_rank = _rank_of_gold(reranked, gold_texts, lambda r: r.text)
        old_ranks[-1] = rerank_old_rank  # 用同一实现跑"不过滤"配置，对照更公平

        reranked_new = await new_reranker.rerank(case.query, chunks, top_k=len(chunks))
        new_rank = _rank_of_gold(reranked_new, gold_texts, lambda r: r.text)
        new_ranks.append(new_rank)

        details.append((case.query, base_rank, rerank_old_rank, new_rank))

    bm, om, nm = _metrics(base_ranks), _metrics(old_ranks), _metrics(new_ranks)

    print("=" * 78)
    print(f"知源检索评测 · 重排策略对比（{len(CASES)} case，每 case 1 条 gold）")
    print("=" * 78)
    print(f"{'指标':<12}{'纯向量':>10}{'旧版(不过滤)':>14}{'新版(归一+过滤)':>18}")
    print("-" * 78)
    for k in ["HitRate@1", "HitRate@3", "HitRate@5", "MRR"]:
        if k == "MRR":
            print(f"{k:<12}{bm[k]:>10.3f}{om[k]:>14.3f}{nm[k]:>18.3f}")
        else:
            print(f"{k:<12}{bm[k]*100:>9.0f}%{om[k]*100:>13.0f}%{nm[k]*100:>17.0f}%")
    print("-" * 78)

    print("\n逐 case gold 排名（0 = 未进候选集）：")
    print(f"{'query':<26}{'纯向量':>8}{'旧版':>8}{'新版':>8}")
    for q, b, o, n in details:
        mark = "  ← 改善" if n < o else ("  ← 变差" if n > o else "")
        print(f"{q[:24]:<26}{b:>8}{o:>8}{n:>8}{mark}")

    print("\n结论：")
    print(f"  · 相对纯向量： MRR {bm['MRR']:.3f} → {nm['MRR']:.3f}，"
          f"HitRate@3 {bm['HitRate@3']*100:.0f}% → {nm['HitRate@3']*100:.0f}%")
    print(f"  · 相对旧版实现：MRR {om['MRR']:.3f} → {nm['MRR']:.3f}，"
          f"HitRate@3 {om['HitRate@3']*100:.0f}% → {nm['HitRate@3']*100:.0f}%")
    print("\n  注：本评测用合成候选数据验证重排算法逻辑；"
          "真实效果需接入 Qdrant + 真实文档标注集。")


if __name__ == "__main__":
    asyncio.run(main())
