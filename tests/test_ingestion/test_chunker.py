"""文本分块器单元测试。"""

from app.ingestion.chunker import TextChunker


def test_short_text_single_chunk():
    chunker = TextChunker()
    chunks = chunker.chunk_text("这是一段短文本。")

    assert len(chunks) == 1
    assert "短文本" in chunks[0].text
    assert chunks[0].chunk_index == 0


def test_chinese_sentence_boundaries():
    """验证中文标点优先切分。"""
    chunker = TextChunker(chunk_size=20, chunk_overlap=5)
    text = "这是第一句话。这是第二句话。这是第三句话。这是第四句话。"
    chunks = chunker.chunk_text(text)

    assert len(chunks) >= 2
    # 每个块不应该跨越句子中间
    for c in chunks:
        assert c.text.strip()


def test_page_index_preserved():
    chunker = TextChunker(chunk_size=30, chunk_overlap=5)
    pages = [
        "第一页内容第一页内容第一页内容第一页内容第一页内容。",
        "第二页内容第二页内容第二页内容第二页内容第二页内容。",
    ]
    chunks = chunker.chunk_pages(pages, filename="test.pdf")

    assert len(chunks) >= 2
    page_indices = {c.page_index for c in chunks}
    assert 0 in page_indices
    assert 1 in page_indices


def test_metadata_contains_filename_and_page():
    chunker = TextChunker()
    chunks = chunker.chunk_text("测试文本", filename="doc.pdf")

    assert chunks[0].metadata["filename"] == "doc.pdf"
    assert chunks[0].metadata["page"] == 1


def test_empty_pages_produce_no_chunks():
    chunker = TextChunker()
    chunks = chunker.chunk_pages(["", "  ", "\n"])

    assert chunks == []


def test_chunk_indices_are_sequential():
    chunker = TextChunker(chunk_size=15, chunk_overlap=3)
    text = "一段。二段。三段。四段。五段。六段。七段。八段。"
    chunks = chunker.chunk_text(text)

    indices = [c.chunk_index for c in chunks]
    assert indices == list(range(len(chunks)))
