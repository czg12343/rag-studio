from __future__ import annotations

import re

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


PAGE_PATTERN = re.compile(r"\[第\s*(\d+)\s*页\]")
SECTION_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$")


def split_text(
    text: str,
    source_file: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> list[Document]:
    if chunk_size <= 0:
        raise ValueError("chunk_size 必须大于 0")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap 必须大于等于 0 且小于 chunk_size")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", "。", "；", "，", ". ", " ", ""],
    )

    # Split at page/heading boundaries first, so a citation cannot cross pages.
    boundaries = sorted({0, len(text)} | {m.start() for m in re.finditer(r"(?m)^(?:\[第\s*\d+\s*页\]|#{1,6}\s+.+)", text)})
    documents: list[Document] = []
    located_chunks = []
    for left, right in zip(boundaries, boundaries[1:]):
        cursor = left
        for chunk in splitter.split_text(text[left:right]):
            start = text.find(chunk, cursor, right)
            if start < 0:
                raise ValueError("无法定位切分片段")
            located_chunks.append((chunk, start))
            cursor = max(start + 1, start + len(chunk) - chunk_overlap)

    for index, (chunk, start) in enumerate(located_chunks):
        if not chunk.strip():
            continue

        end = start + len(chunk)

        documents.append(
            Document(
                page_content=chunk,
                metadata={
                    "source": source_file,
                    "chunk_index": index,
                    "char_start": start,
                    "char_end": end,
                    "page": _page_for_position(text, start) or 0,
                    "section": _section_for_position(text, start),
                    "length": len(chunk),
                },
            )
        )

    return documents


def _page_for_position(text: str, position: int) -> int | None:
    page = None
    for match in PAGE_PATTERN.finditer(text):
        if match.start() > position:
            break
        page = int(match.group(1))
    return page


def _section_for_position(text: str, position: int) -> str:
    section = ""
    line_end = text.find("\n", position)
    prefix = text[:line_end if line_end >= 0 else len(text)]
    for line in prefix.splitlines():
        match = SECTION_PATTERN.match(line.strip())
        if match:
            section = match.group(2).strip()
    return section
