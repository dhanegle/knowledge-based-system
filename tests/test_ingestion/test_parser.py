"""文档解析器单元测试。"""

from pathlib import Path

from app.ingestion.parser import DocumentParser


def test_parse_markdown(tmp_path: Path):
    md = tmp_path / "test.md"
    md.write_text("# 标题\n\n这是内容。", encoding="utf-8")

    result = DocumentParser().parse(md)

    assert result.filename == "test.md"
    assert result.file_type == ".md"
    assert len(result.pages) == 1
    assert "标题" in result.pages[0]
    assert "内容" in result.pages[0]


def test_parse_python_code(tmp_path: Path):
    py = tmp_path / "auth.py"
    py.write_text("def login():\n    pass\n", encoding="utf-8")

    result = DocumentParser().parse(py)

    assert result.file_type == ".py"
    assert "def login" in result.pages[0]


def test_parse_txt(tmp_path: Path):
    txt = tmp_path / "notes.txt"
    txt.write_text("第一条笔记\n第二条笔记\n", encoding="utf-8")

    result = DocumentParser().parse(txt)

    assert result.file_type == ".txt"
    assert "第一条笔记" in result.pages[0]


def test_unsupported_format_raises(tmp_path: Path):
    fake = tmp_path / "data.csv"
    fake.write_text("a,b,c\n1,2,3", encoding="utf-8")

    import pytest
    with pytest.raises(ValueError, match="不支持"):
        DocumentParser().parse(fake)


def test_missing_file_raises():
    import pytest
    with pytest.raises(FileNotFoundError):
        DocumentParser().parse("nonexistent_file.xyz")


def test_parse_docx(tmp_path: Path):
    """测试 Word 文档解析（用 python-docx 生成测试文件）。"""
    from docx import Document as DocxDocument

    docx_path = tmp_path / "test.docx"
    doc = DocxDocument()
    doc.add_paragraph("第一段内容")
    doc.add_paragraph("第二段内容")
    doc.save(str(docx_path))

    result = DocumentParser().parse(docx_path)

    assert result.file_type == ".docx"
    assert "第一段内容" in result.pages[0]
    assert "第二段内容" in result.pages[0]


def test_parse_xlsx(tmp_path: Path):
    """测试 Excel 解析。"""
    from openpyxl import Workbook

    xlsx_path = tmp_path / "test.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["姓名", "年龄"])
    ws.append(["张三", 30])
    wb.save(str(xlsx_path))

    result = DocumentParser().parse(xlsx_path)

    assert result.file_type == ".xlsx"
    assert "张三" in result.pages[0]
    assert "姓名" in result.pages[0]
