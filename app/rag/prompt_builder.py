"""RAG Prompt 构建：把检索到的文本块拼成带引用指令的系统 prompt。"""

from __future__ import annotations

from app.retrieval.reranker import RerankedChunk

SYSTEM_PROMPT = """你是「知源」，一个公司知识库问答助手。请根据下面提供的参考信息回答用户问题。

要求：
1. 只基于参考信息回答，不要编造未在参考信息中出现的内容。
2. 如果参考信息不足以回答问题，明确说"根据现有知识库，我无法回答这个问题"。
3. 回答中不要使用 Markdown 格式（不要用 ** 加粗、# 标题、- 列表符等），直接用纯文本回答。
4. 不要在回答中标注来源文件名或页码，来源信息会由前端单独展示。
5. 用与问题相同的语言回答（中文问题用中文回答）。
6. 回答简洁准确，不要过度展开。"""


def build_context(chunks: list[RerankedChunk]) -> str:
    """把重排后的文本块拼成上下文文本，带编号和来源标注。"""
    if not chunks:
        return ""

    parts: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        source = f"{chunk.filename}, 第{chunk.page}页"
        parts.append(
            f"[参考{i}] 来源: {source}\n{chunk.text}"
        )
    return "\n\n---\n\n".join(parts)


def build_user_message(question: str, context: str) -> str:
    """构建用户消息：上下文 + 问题。"""
    if not context:
        return question
    return f"参考信息：\n\n{context}\n\n---\n\n用户问题：{question}"
