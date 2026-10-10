"""Validated, local runtime settings. Paths never depend on the launch directory."""
import json
import os
from pathlib import Path
from threading import RLock
from typing import Literal

from pydantic import BaseModel, Field, model_validator

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("RAG_DATA_DIR", str(ROOT / "data"))).resolve()
SETTINGS_PATH = DATA_DIR / "settings.json"
STATE_LOCK = RLock()  # One local process; run uvicorn with one worker.


class Settings(BaseModel):
    embedding_backend: Literal["hash", "sentence-transformers"] = "hash"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_revision: str = "local-v1"
    chunk_size: int = Field(500, ge=100, le=4000)
    chunk_overlap: int = Field(50, ge=0, le=1000)
    top_k: int = Field(4, ge=1, le=20)
    candidate_k: int = Field(20, ge=1, le=100)
    reranker: Literal["none", "lightweight", "semantic"] = "lightweight"
    reranker_model: str = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
    history_chars: int = Field(6000, ge=0, le=20000)
    history_turns: int = Field(6, ge=0, le=20)

    @model_validator(mode="after")
    def validate_ranges(self):
        if self.chunk_overlap >= self.chunk_size or self.candidate_k < self.top_k:
            raise ValueError("切分重叠必须小于片段长度，候选数必须不小于 Top-K")
        if not self.embedding_model.strip() or not self.embedding_revision.strip():
            raise ValueError("模型名称和版本不能为空")
        return self


def get_settings() -> Settings:
    if SETTINGS_PATH.exists():
        return Settings.model_validate_json(SETTINGS_PATH.read_text(encoding="utf-8"))
    values = {key: os.environ[key.upper()] for key in Settings.model_fields if key.upper() in os.environ}
    return Settings(**values)


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)


def save_settings(settings: Settings) -> Settings:
    with STATE_LOCK:
        atomic_json(SETTINGS_PATH, settings.model_dump())
    return settings


def embedding_signature() -> dict:
    config = get_settings()
    if config.embedding_backend == "hash":
        return {"backend": "hash", "model": "blake2b-1024", "revision": "1"}
    return {"backend": config.embedding_backend, "model": config.embedding_model,
            "revision": config.embedding_revision}
