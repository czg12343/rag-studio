from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".markdown"}


@dataclass(frozen=True)
class LoadedDocument:
    source_path: Path
    source_name: str
    text: str


def load_document(file_path: str | Path) -> LoadedDocument:
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValueError(f"不支持的文件类型: {suffix}，当前支持: {supported}")

    if suffix == ".pdf":
        text = _load_pdf(path)
    elif suffix == ".docx":
        text = _load_docx(path)
    else:
        text = _load_text(path)

    text = _clean_text(text)
    if not text:
        raise ValueError("文档没有解析出有效文本，请检查文件内容是否可复制，或是否为扫描件。")

    return LoadedDocument(source_path=path, source_name=path.name, text=text)


def _load_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages: list[str] = []
    for page_number, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        if page_text.strip():
            pages.append(f"[第 {page_number} 页]\n{page_text}")
    return "\n\n".join(pages)


def _load_docx(path: Path) -> str:
    from docx import Document as DocxDocument
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    import zipfile

    with zipfile.ZipFile(path) as archive:
        if sum(item.file_size for item in archive.infolist()) > 100 * 1024 * 1024:
            raise ValueError("DOCX 解压后过大")

    document = DocxDocument(str(path))
    parts: list[str] = []

    table_index = 0
    for element in document.element.body:
        if element.tag.endswith("}p"):
            paragraph = Paragraph(element, document)
            text = paragraph.text.strip()
            if text:
                style = paragraph.style.name if paragraph.style else ""
                parts.append(f"\n# {text}" if style.lower().startswith("heading") else text)
        elif element.tag.endswith("}tbl"):
            table_index += 1
            parts.append(f"\n[表格 {table_index}]")
            for row in Table(element, document).rows:
                parts.append(" | ".join(cell.text.strip() for cell in row.cells))

    return "\n".join(parts)


def _load_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            text = path.read_text(encoding=encoding)
            if "\x00" in text:
                raise ValueError("文本文件含有二进制内容")
            return text
        except UnicodeDecodeError:
            continue
    raise ValueError("文本编码无法识别，请转换为 UTF-8")


def _clean_text(text: str) -> str:
    lines = [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    compact_lines: list[str] = []
    previous_blank = False

    for line in lines:
        is_blank = not line
        if is_blank and previous_blank:
            continue
        compact_lines.append(line)
        previous_blank = is_blank

    return "\n".join(compact_lines).strip()
