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


def test_parse_pptx_includes_table_and_text(tmp_path: Path):
    """PPT 表格此前因 GraphicFrame 无 .text 属性被静默丢弃，回归验证。"""
    from pptx import Presentation
    from pptx.util import Inches

    pptx_path = tmp_path / "report.pptx"
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # 空白版式
    box = slide.shapes.add_textbox(Inches(1), Inches(0.2), Inches(4), Inches(0.5))
    box.text_frame.text = "季度汇报"
    frame = slide.shapes.add_table(2, 2, Inches(1), Inches(1), Inches(4), Inches(2))
    table = frame.table
    table.cell(0, 0).text = "项目"
    table.cell(0, 1).text = "进度"
    table.cell(1, 0).text = "摄入管线"
    table.cell(1, 1).text = "已完成"
    prs.save(str(pptx_path))

    result = DocumentParser().parse(pptx_path)

    text = result.pages[0]
    assert "季度汇报" in text
    assert "项目 | 进度" in text
    assert "摄入管线 | 已完成" in text


def test_parse_xlsx_sheet_prefix_and_header_alignment(tmp_path: Path):
    """多 sheet 时 sheet 名进每行前缀；数据行对齐成"列名: 值"。"""
    from openpyxl import Workbook

    xlsx_path = tmp_path / "sales.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "员工"
    ws.append(["姓名", "年龄"])
    ws.append(["张三", 30])
    ws2 = wb.create_sheet("销售")
    ws2.append(["产品", "数量"])
    ws2.append(["键盘", 12])
    wb.save(str(xlsx_path))

    result = DocumentParser().parse(xlsx_path)
    text = result.pages[0]

    assert "[工作表 员工] 表头: 姓名 | 年龄" in text
    assert "[工作表 员工] 姓名: 张三 | 年龄: 30" in text
    assert "[工作表 销售] 表头: 产品 | 数量" in text
    assert "[工作表 销售] 产品: 键盘 | 数量: 12" in text


def test_parse_xlsx_sparse_columns_keep_position(tmp_path: Path):
    """行中间有空单元格时按列位置对齐表头，不错位。"""
    from openpyxl import Workbook

    xlsx_path = tmp_path / "sparse.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "数据"
    ws.append(["名称", "备注", "数量"])
    ws.append(["螺丝", None, 100])  # 中间列为空
    wb.save(str(xlsx_path))

    result = DocumentParser().parse(xlsx_path)
    text = result.pages[0]

    assert "[工作表 数据] 名称: 螺丝 | 数量: 100" in text
