"""文档解析器：将各种格式的文件提取为纯文本。

支持格式：PDF / Word(.docx) / PPT(.pptx) / Excel(.xlsx) / Markdown / 纯文本 / 代码。
每种格式用对应的库解析，返回统一的 Document 结构。

- pages 列表按文档页序对齐：索引 i 恰好是第 i+1 页，纯图片页占位空串，
  供摄入管线按页码回填视觉识别结果。
- 表格统一转成 "单元格 | 单元格" 的行文本，保住行内列对应关系。
- PDF 用 pdfplumber：表格按线框识别为结构化行，表格区域的字符从正文剔除
  （否则同一段内容会以乱序文本流和结构化行重复出现）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".pptx", ".xlsx", ".md", ".txt",
    ".py", ".js", ".ts", ".java", ".go", ".rs", ".c", ".cpp", ".h",
    ".sql", ".sh", ".yaml", ".yml", ".json", ".xml", ".html", ".css",
}


@dataclass
class ParsedDocument:
    """解析后的文档。"""
    filename: str
    file_type: str          # 扩展名，如 ".pdf"
    pages: list[str]        # 按页分割的文本（索引 i = 第 i+1 页；纯图片页为空串）
    # 纯图片页的页码（1-based，扫描件或纯图片页），文字未提取
    image_only_pages: list[int] = field(default_factory=list)


def _clean_cell(value) -> str:
    """表格单元格文本压成单行，None 视为空。"""
    if value is None:
        return ""
    return str(value).replace("\n", " ").strip()


def _obj_in_bboxes(obj: dict, bboxes: list[tuple]) -> bool:
    """按对象中心点判断是否落在任一表格框内（容差 1pt）。"""
    cx = (obj["x0"] + obj["x1"]) / 2
    cy = (obj["top"] + obj["bottom"]) / 2
    return any(
        x0 - 1 <= cx <= x1 + 1 and top - 1 <= cy <= bottom + 1
        for x0, top, x1, bottom in bboxes
    )


class DocumentParser:
    """统一文档解析器，根据扩展名分派到对应的解析方法。"""

    def parse(self, filepath: str | Path) -> ParsedDocument:
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")

        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"不支持的文件格式: {ext}（支持: {', '.join(sorted(SUPPORTED_EXTENSIONS))}）")

        pages, image_only_pages = self._extract(path, ext)
        if image_only_pages:
            logger.warning("%s 含纯图片页（文字未提取）: %s", path.name, image_only_pages)

        logger.info("解析完成 %s (%s) → %d 页, %d 字符",
                     path.name, ext, len(pages), sum(len(p) for p in pages))
        return ParsedDocument(
            filename=path.name,
            file_type=ext,
            pages=pages,
            image_only_pages=image_only_pages,
        )

    def _extract(self, path: Path, ext: str) -> tuple[list[str], list[int]]:
        """提取文本，返回 (按页文本列表, 纯图片页码列表)。"""
        extractors = {
            ".pdf": self._extract_pdf,
            ".docx": self._extract_docx,
            ".pptx": self._extract_pptx,
            ".xlsx": self._extract_xlsx,
        }
        extractor = extractors.get(ext, self._extract_text)
        return extractor(path)

    def _extract_pdf(self, path: Path) -> tuple[list[str], list[int]]:
        import pdfplumber

        pages: list[str] = []
        image_only_pages: list[int] = []

        with pdfplumber.open(str(path)) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                segments: list[str] = []
                try:
                    tables = page.find_tables()
                    if tables:
                        # 表格区域内的字符从正文剔除，避免内容重复
                        bboxes = [t.bbox for t in tables]
                        text = page.filter(
                            lambda obj, boxes=bboxes: not _obj_in_bboxes(obj, boxes)
                        ).extract_text() or ""
                    else:
                        text = page.extract_text() or ""
                    if text.strip():
                        segments.append(text.strip())
                    for table in tables:
                        rows = [
                            " | ".join(_clean_cell(c) for c in row)
                            for row in table.extract()
                        ]
                        rows = [r for r in rows if r.strip(" |")]
                        if rows:
                            segments.append("[表格]\n" + "\n".join(rows))
                except Exception:
                    logger.warning(
                        "%s 第 %d 页结构化提取异常，跳过表格仅尽力保留文本",
                        path.name, i, exc_info=True,
                    )

                if segments:
                    pages.append("\n\n".join(segments))
                else:
                    if page.images:
                        image_only_pages.append(i)
                    logger.warning("%s 第 %d 页无文本（可能是扫描件，需要 OCR）", path.name, i)
                    # 占位空串，保证 pages[i-1] 与页码对齐，供视觉识别回填
                    pages.append("")

        return pages, image_only_pages

    def _extract_docx(self, path: Path) -> tuple[list[str], list[int]]:
        from docx import Document as DocxDocument
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        doc = DocxDocument(str(path))
        parts: list[str] = []
        # 按文档实际顺序交错输出段落与表格，保住"表和它的上下文说明"相邻
        for block in doc.iter_inner_content():
            if isinstance(block, Table):
                parts.extend(self._render_table(block))
            elif isinstance(block, Paragraph) and block.text.strip():
                parts.append(block.text.strip())
        text = "\n".join(parts)
        return ([text] if text.strip() else []), []

    def _render_table(self, table) -> list[str]:
        """表格转文本行；嵌套表在所属行之后独立成行（递归）。"""
        lines: list[str] = []
        for row in table.rows:
            cells: list[str] = []
            nested: list[str] = []
            prev_tc = None
            for cell in row.cells:
                # 合并单元格在同一行按其跨的列数重复出现，按底层元素去重
                if cell._tc is prev_tc:
                    continue
                prev_tc = cell._tc
                inline, cell_nested = self._render_cell(cell)
                cells.append(inline)
                nested.extend(cell_nested)
            row_text = " | ".join(cells)
            if row_text.strip():
                lines.append(row_text)
            lines.extend(nested)
        return lines

    def _render_cell(self, cell) -> tuple[str, list[str]]:
        """单元格 → (行内文本, 嵌套表的文本行)。"""
        from docx.table import Table

        inline: list[str] = []
        nested: list[str] = []
        for block in cell.iter_inner_content():
            if isinstance(block, Table):
                nested.extend(self._render_table(block))
            elif block.text.strip():
                inline.append(block.text.strip())
        return " ".join(inline), nested

    def _extract_pptx(self, path: Path) -> tuple[list[str], list[int]]:
        from pptx import Presentation
        from pptx.enum.shapes import MSO_SHAPE_TYPE

        prs = Presentation(str(path))
        pages: list[str] = []
        image_only_pages: list[int] = []
        for i, slide in enumerate(prs.slides, 1):
            slide_texts: list[str] = []
            has_picture = False
            for shape in slide.shapes:
                # 表格/图表是 GraphicFrame 容器，没有 .text 属性，
                # 不单独处理会被静默跳过
                if shape.has_table:
                    slide_texts.extend(self._table_to_lines(shape.table))
                elif hasattr(shape, "text") and shape.text.strip():
                    slide_texts.append(shape.text)
                if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                    has_picture = True
            if slide_texts:
                pages.append("\n".join(slide_texts))
            else:
                if has_picture:
                    image_only_pages.append(i)
                    logger.warning("%s 第 %d 页只有图片，文字未提取", path.name, i)
                pages.append("")
        return pages, image_only_pages

    def _extract_xlsx(self, path: Path) -> tuple[list[str], list[int]]:
        from openpyxl import load_workbook

        wb = load_workbook(str(path), read_only=True, data_only=True)
        parts: list[str] = []
        for ws in wb.worksheets:
            lines = self._worksheet_to_lines(ws)
            if lines:
                parts.append("\n".join(lines))
        wb.close()
        text = "\n".join(parts)
        return ([text] if text.strip() else []), []

    def _extract_text(self, path: Path) -> tuple[list[str], list[int]]:
        """Markdown、纯文本、代码文件统一用 UTF-8 读取。"""
        text = path.read_text(encoding="utf-8", errors="replace")
        return ([text] if text.strip() else []), []

    @staticmethod
    def _table_to_lines(table) -> list[str]:
        """表格逐行转 '单元格 | 单元格' 文本，保住行内列对应关系（docx/pptx 通用）。"""
        lines: list[str] = []
        for row in table.rows:
            row_text = " | ".join(cell.text.strip() for cell in row.cells)
            if row_text.strip():
                lines.append(row_text)
        return lines

    @staticmethod
    def _worksheet_to_lines(ws) -> list[str]:
        """工作表转文本：sheet 名进每行前缀；首个非空行视为表头，
        数据行尽量对齐成 "列名: 值"，让分块后的片段自带列语义，
        不再依赖表头与数据恰好被分进同一个块。"""
        prefix = f"[工作表 {ws.title}] "
        lines: list[str] = []
        header: list[str] = []

        for row in ws.iter_rows(values_only=True):
            # 按列位置收集非空单元格，避免过滤 None 后错位
            cells = [
                (i, str(c).strip())
                for i, c in enumerate(row)
                if c is not None and str(c).strip()
            ]
            if not cells:
                continue

            if not header:
                header = [""] * (max(i for i, _ in cells) + 1)
                for i, v in cells:
                    header[i] = v
                lines.append(prefix + "表头: " + " | ".join(v for v in header if v))
                continue

            body = " | ".join(
                f"{header[i]}: {v}" if i < len(header) and header[i] else v
                for i, v in cells
            )
            lines.append(prefix + body)

        return lines
