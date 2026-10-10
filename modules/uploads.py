"""Validate before touching user files; retain replaced originals as backups."""
import re
import tempfile
import uuid
from pathlib import Path

from modules.document_loader import SUPPORTED_EXTENSIONS, load_document
from modules.settings import DATA_DIR, STATE_LOCK, get_settings
from modules.text_splitter import split_text
from modules.vector_store import index_documents, delete_source

UPLOAD_DIR = DATA_DIR / "uploads"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def safe_filename(name: str) -> str:
    if (not name or len(name) > 180 or name != name.strip() or
            re.search(r'[\\/:*?"<>|\x00-\x1f]', name) or name.endswith((".", " ")) or
            name.startswith(".") or re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", name, re.I)):
        raise ValueError("文件名不安全，请使用不含路径和特殊字符的文件名")
    if Path(name).suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError("仅支持 PDF、DOCX、TXT 和 Markdown 文件")
    return name


def ingest_bytes(name: str, content: bytes, chunk_size: int | None = None, chunk_overlap: int | None = None) -> dict:
    name = safe_filename(name)
    if not content or len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("文件不能为空且不得超过 20 MiB")
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf" and not content.startswith(b"%PDF-"):
        raise ValueError("PDF 文件内容与扩展名不符")
    if suffix == ".docx" and not content.startswith(b"PK"):
        raise ValueError("DOCX 文件内容与扩展名不符")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with STATE_LOCK, tempfile.TemporaryDirectory(dir=UPLOAD_DIR) as temp:
        staged = Path(temp) / name
        staged.write_bytes(content)
        try:
            loaded = load_document(staged)
        except Exception as exc:
            raise ValueError("文件内容无法解析") from exc
        config = get_settings()
        docs = split_text(loaded.text, name, chunk_size if chunk_size is not None else config.chunk_size,
                          chunk_overlap if chunk_overlap is not None else config.chunk_overlap)
        destination = UPLOAD_DIR / name
        backup = None
        if destination.exists():
            backup = DATA_DIR / "backups" / f"{uuid.uuid4().hex}-{name}"
            backup.parent.mkdir(parents=True, exist_ok=True)
            destination.replace(backup)
        try:
            staged.replace(destination)
            chunks = index_documents(docs, name)
        except Exception:
            destination.unlink(missing_ok=True)
            if backup:
                backup.replace(destination)
            raise
    return {"source": name, "chunks": chunks}


def reindex_source(name: str) -> dict:
    name = safe_filename(name)
    path = UPLOAD_DIR / name
    if not path.is_file():
        raise FileNotFoundError("原文件不存在，请重新上传")
    return ingest_bytes(name, path.read_bytes())


def archive_document(name: str) -> dict:
    name = safe_filename(name)
    with STATE_LOCK:
        path = UPLOAD_DIR / name
        backup = None
        if path.is_file():
            backup = DATA_DIR / "backups" / f"{uuid.uuid4().hex}-{name}"
            backup.parent.mkdir(parents=True, exist_ok=True)
            path.replace(backup)
        try:
            deleted = delete_source(name)
        except Exception:
            if backup:
                backup.replace(path)
            raise
        return {"source": name, "deleted": deleted, "original_archived": backup is not None}
