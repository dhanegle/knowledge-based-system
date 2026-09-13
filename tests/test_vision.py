"""图片页视觉识别测试：客户端（MockTransport）、取图、notes 汇总、管线回填。"""

import httpx
import pytest

from app.ingestion.parser import ParsedDocument
from app.llm.vision import (
    VisionClient,
    get_vision_client,
    reset_vision_client,
)
from tests.test_ingestion.test_parser import _PDF_TEXT_PAGE, _build_pdf


def _mock_transport(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_vision_client_extracts_content():
    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        assert b"data:image/png;base64," in body
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "识别出的文字"}}]
        })

    client = VisionClient(
        "https://example.test/v1", "key", "vision-model",
        http_client=_mock_transport(handler),
    )
    assert await client.extract_text(b"fakeimage", "image/png", page_no=3) == "识别出的文字"


async def test_vision_client_returns_none_on_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "no vision"}})

    client = VisionClient(
        "https://example.test/v1", "key", "text-model",
        http_client=_mock_transport(handler),
    )
    assert await client.extract_text(b"img", "image/png") is None


async def test_vision_client_returns_none_on_empty_content():
    """推理模型 max_tokens 耗尽时 content 为空，应视为识别失败。"""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": ""}}]})

    client = VisionClient(
        "https://example.test/v1", "key", "reasoning-model",
        http_client=_mock_transport(handler),
    )
    assert await client.extract_text(b"img", "image/png") is None


def test_get_vision_client_none_without_llm(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "llm_base_url", "")
    reset_vision_client()
    try:
        assert get_vision_client() is None
    finally:
        reset_vision_client()


def test_collect_pdf_page_images(tmp_path):
    """PDF 图片页栅格化为 JPEG 负载；预算为 0 时不取图。"""
    from app.ingestion.page_images import collect_page_images

    pdf_path = tmp_path / "scan.pdf"
    image_draw = "q 200 0 0 200 100 400 cm /Im1 Do Q"
    pdf_path.write_bytes(_build_pdf([_PDF_TEXT_PAGE, image_draw], image_page=1))

    images = collect_page_images(str(pdf_path), [2], max_requests=5)
    assert set(images) == {2}
    (blob, mime), = images[2]
    assert mime == "image/jpeg"
    assert blob[:2] == b"\xff\xd8"  # JPEG 魔数

    assert collect_page_images(str(pdf_path), [2], max_requests=0) == {}


@pytest.mark.asyncio
async def test_pipeline_recognizes_and_splices_image_pages(monkeypatch, tmp_path):
    """管线把识别文本回填到对应页；未配置视觉客户端时不回填。"""
    import app.embedding.base as emb_mod
    import app.llm.vision as vision_mod
    import app.storage.qdrant as qdrant_mod
    from app.config import settings
    from app.ingestion.pipeline import IngestionPipeline, _build_extraction_notes
    from app.embedding.base import StubEmbeddingService

    pdf_path = tmp_path / "scan.pdf"
    image_draw = "q 200 0 0 200 100 400 cm /Im1 Do Q"
    pdf_path.write_bytes(_build_pdf([_PDF_TEXT_PAGE, image_draw], image_page=1))

    # 隔离外部依赖：embedding/qdrant 换桩，视觉客户端换假实现
    monkeypatch.setattr(emb_mod, "_embedding_service", StubEmbeddingService(dim=8))
    monkeypatch.setattr(qdrant_mod, "_store", object())
    monkeypatch.setattr(settings, "vision_max_pages", 5)

    class FakeVision:
        async def extract_text(self, image, mime, *, page_no=None):
            return f"第{page_no}页识别文本"

    monkeypatch.setattr(vision_mod, "_client", FakeVision())

    pipeline = IngestionPipeline()
    parsed = ParsedDocument(
        filename="scan.pdf", file_type=".pdf",
        pages=["ZhiYuan knowledge base", ""], image_only_pages=[2],
    )

    recognized = await pipeline._recognize_image_pages(str(pdf_path), parsed)

    assert recognized == {2: "第2页识别文本"}
    assert parsed.pages[1] == "第2页识别文本"
    assert _build_extraction_notes(parsed, recognized) == "第 2 页图片内容已识别"
    assert _build_extraction_notes(parsed, {}) == (
        "第 2 页为图片页（扫描件或纯图片），文字未提取"
    )


def test_build_extraction_notes_mixed():
    from app.ingestion.pipeline import _build_extraction_notes

    parsed = ParsedDocument(
        filename="a.pdf", file_type=".pdf",
        pages=["", "", ""], image_only_pages=[1, 2, 3],
    )
    notes = _build_extraction_notes(parsed, recognized={1: "ok"})
    assert notes == "第 1 页图片内容已识别；第 2、3 页为图片页（扫描件或纯图片），文字未提取"

    assert _build_extraction_notes(
        ParsedDocument(filename="b", file_type=".pdf", pages=["x"], image_only_pages=[]),
    ) is None
