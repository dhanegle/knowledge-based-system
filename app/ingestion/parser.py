"""文档解析器：将各种格式的文件提取为纯文本。

支持格式：PDF / Word(.docx) / PPT(.pptx) / Excel(.xlsx) / Markdown / 纯文本 / 代码。
每种格式用对应的库解析，返回统一的 Document 结构。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
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
    pages: list[str]        # 按页分割的文本（PDF/PPT 有页概念；其他格式整篇为 1 页）


class DocumentParser:
    """统一文档解析器，根据扩展名分派到对应的解析方法。"""

    def parse(self, filepath: str | Path) -> ParsedDocument:
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")

        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"不支持的文件格式: {ext}（支持: {', '.join(sorted(SUPPORTED_EXTENSIONS))}）")

        text = self._extract(path, ext)
        pages = self._split_pages(text, ext)

        logger.info("解析完成 %s (%s) → %d 页, %d 字符",
                     path.name, ext, len(pages), sum(len(p) for p in pages))
        return ParsedDocument(filename=path.name, file_type=ext, pages=pages)

    def _extract(self, path: Path, ext: str) -> str:
        extractors = {
            ".pdf": self._extract_pdf,
            ".docx": self._extract_docx,
            ".pptx": self._extract_pptx,
            ".xlsx": self._extract_xlsx,
        }
        extractor = extractors.get(ext, self._extract_text)
        return extractor(path)

    def _extract_pdf(self, path: Path) -> str:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        parts: list[str] = []
        for i, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            if text.strip():
                parts.append(f"--- 第 {i} 页 ---\n{text}")
            else:
                logger.warning("%s 第 %d 页无文本（可能是扫描件，需要 OCR）", path.name, i)
        return "\n\n".join(parts)

    def _extract_docx(self, path: Path) -> str:
        from docx import Document as DocxDocument

        doc = DocxDocument(str(path))
        parts: list[str] = []
        for para in doc.paragraphs:
            if para.text.strip():
                parts.append(para.text)

        for table in doc.tables:
            parts.extend(self._table_to_lines(table))
        return "\n".join(parts)

    def _extract_pptx(self, path: Path) -> str:
        from pptx import Presentation

        prs = Presentation(str(path))
        parts: list[str] = []
        for i, slide in enumerate(prs.slides, 1):
            slide_texts: list[str] = []
            for shape in slide.shapes:
                # 表格/图表是 GraphicFrame 容器，没有 .text 属性，
                # 不单独处理会被静默跳过
                if shape.has_table:
                    slide_texts.extend(self._table_to_lines(shape.table))
                elif hasattr(shape, "text") and shape.text.strip():
                    slide_texts.append(shape.text)
            if slide_texts:
                parts.append(f"--- 第 {i} 页 ---\n" + "\n".join(slide_texts))
        return "\n\n".join(parts)

    def _extract_xlsx(self, path: Path) -> str:
        from openpyxl import load_workbook

        wb = load_workbook(str(path), read_only=True, data_only=True)
        parts: list[str] = []
        for ws in wb.worksheets:
            lines = self._worksheet_to_lines(ws)
            if lines:
                parts.append("\n".join(lines))
        wb.close()
        return "\n".join(parts)

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

    def _extract_text(self, path: Path) -> str:
        """Markdown、纯文本、代码文件统一用 UTF-8 读取。"""
        return path.read_text(encoding="utf-8", errors="replace")

    def _split_pages(self, text: str, ext: str) -> list[str]:
        """PDF 和 PPT 用 --- 第 N 页 --- 标记分页；其他格式整篇为 1 页。"""
        if ext in (".pdf", ".pptx"):
            import re
            pages = re.split(r"^--- 第 \d+ 页 ---$", text, flags=re.MULTILINE)
            pages = [p.strip() for p in pages if p.strip()]
            return pages or [text]
        return [text] if text.strip() else []
