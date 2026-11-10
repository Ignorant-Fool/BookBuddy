"""
文档加载 —— 把 txt / md / docx / doc / pptx / ppt / pdf 统一成 LangChain Document。
"""
from __future__ import annotations

import logging
from pathlib import Path

from langchain_core.documents import Document

from config import ALLOWED_UPLOAD_EXT

logger = logging.getLogger(__name__)


class UnsupportedFormatError(ValueError):
    pass


def load_document(path: str | Path, source_name: str | None = None) -> Document:
    """按扩展名提取纯文本，返回单个 Document（后续由切片器切分）。"""
    path = Path(path)
    ext = path.suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXT:
        raise UnsupportedFormatError(f"不支持的文件格式: {ext}")

    if ext in (".txt", ".md"):
        text = _load_text(path)
    elif ext in (".docx", ".doc"):
        text = _load_docx(path)
    elif ext in (".pptx", ".ppt"):
        text = _load_pptx(path)
    else:
        text = _load_pdf(path)

    text = _normalize(text)
    if not text.strip():
        raise ValueError("文档内容为空，无法提取文本")

    return Document(
        page_content=text,
        metadata={
            "source": source_name or path.name,
            "filename": path.name,
            "extension": ext,
        },
    )


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u3000", " ")
    # 折叠 3 个以上空行为 2 个，保留段落边界
    out_lines: list[str] = []
    blank = 0
    for line in text.split("\n"):
        if line.strip():
            blank = 0
            out_lines.append(line.rstrip())
        else:
            blank += 1
            if blank <= 2:
                out_lines.append("")
    return "\n".join(out_lines).strip()


def _load_text(path: Path) -> str:
    for enc in ("utf-8", "utf-8-sig", "gb18030", "big5", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return path.read_bytes().decode("utf-8", errors="ignore")


def _load_docx(path: Path) -> str:
    from docx import Document as DocxDocument

    doc = DocxDocument(str(path))
    parts: list[str] = []
    for para in doc.paragraphs:
        if para.text.strip():
            parts.append(para.text.strip())
    # 表格内容也纳入
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n\n".join(parts)


def _load_pptx(path: Path) -> str:
    from pptx import Presentation

    prs = Presentation(str(path))
    parts: list[str] = []
    for index, slide in enumerate(prs.slides, 1):
        slide_lines: list[str] = []
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False):
                for para in shape.text_frame.paragraphs:
                    t = "".join(run.text for run in para.runs).strip() or para.text.strip()
                    if t:
                        slide_lines.append(t)
        if slide_lines:
            parts.append(f"【第 {index} 页】\n" + "\n".join(slide_lines))
    return "\n\n".join(parts)


def _load_pdf(path: Path) -> str:
    import pdfplumber

    parts: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for index, page in enumerate(pdf.pages, 1):
            try:
                text = page.extract_text() or ""
            except Exception as exc:
                logger.warning("PDF 第 %d 页解析失败: %s", index, exc)
                text = ""
            if text.strip():
                parts.append(text.strip())
    return "\n\n".join(parts)
