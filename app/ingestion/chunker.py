"""中文感知的文本分块器。

用 RecursiveCharacterTextSplitter，分隔符包含中文标点（。！？；），
chunk_size 按字符算（中文一个字≈1-2 token），500 字符是中文的最佳粒度。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from langchain_text_splitters import RecursiveCharacterTextSplitter

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

CHINESE_SEPARATORS: list[str] = [
    "\n\n", "\n",
    "。", "！", "？",
    ".", "!", "?",
    "；", ";",
    "，", ",",
    " ", "",
]


@dataclass
class TextChunk:
    """分块后的文本片段。"""
    text: str
    page_index: int       # 来自第几页（0-based）
    chunk_index: int      # 在该文档内的序号
    metadata: dict        # 额外元数据


class TextChunker:
    """将文档文本按中文语义边界分块。"""

    def __init__(self, chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP):
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=CHINESE_SEPARATORS,
            is_separator_regex=False,
        )

    def chunk_pages(self, pages: Sequence[str], filename: str = "") -> list[TextChunk]:
        """对多页文档分块，保留页码信息。"""
        all_chunks: list[TextChunk] = []
        chunk_idx = 0

        for page_idx, page_text in enumerate(pages):
            if not page_text.strip():
                continue
            pieces = self._splitter.split_text(page_text)
            for piece in pieces:
                if not piece.strip():
                    continue
                all_chunks.append(TextChunk(
                    text=piece,
                    page_index=page_idx,
                    chunk_index=chunk_idx,
                    metadata={"filename": filename, "page": page_idx + 1},
                ))
                chunk_idx += 1

        return all_chunks

    def chunk_text(self, text: str, filename: str = "") -> list[TextChunk]:
        """对单段文本分块。"""
        return self.chunk_pages([text], filename=filename)
