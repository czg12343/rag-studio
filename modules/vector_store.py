from __future__ import annotations

import hashlib
import math
import os
import re
import json
import uuid
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from chromadb.config import Settings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from modules.settings import DATA_DIR, STATE_LOCK, atomic_json, embedding_signature, get_settings


DEFAULT_COLLECTION_NAME = "rag_documents"
DEFAULT_VECTOR_DIR = DATA_DIR / "vector_store"
MANIFEST_PATH = DEFAULT_VECTOR_DIR / "active.json"


class IndexCompatibilityError(ValueError):
    pass


def index_status() -> dict:
    active = _manifest()
    return {"current": embedding_signature(), "indexed": active["embedding"],
            "compatible": active["embedding"] == embedding_signature(),
            "collection": active["collection"]}


def _manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    # Existing V1 code used this exact deterministic hash representation.
    return {"collection": DEFAULT_COLLECTION_NAME,
            "embedding": {"backend": "hash", "model": "blake2b-1024", "revision": "1"}}


def _check_compatible() -> None:
    if not index_status()["compatible"]:
        raise IndexCompatibilityError("Embedding 模型或版本已变化，请执行全库重建；旧索引仍保留，可用 BM25 检索")


class LocalHashEmbeddings(Embeddings):
    """Offline embedding for demos: deterministic hashed character/word features."""

    def __init__(self, dimension: int = 1024) -> None:
        self.dimension = dimension

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in tokenize(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            raw = int.from_bytes(digest, byteorder="big", signed=False)
            index = raw % self.dimension
            sign = 1.0 if ((raw >> 10) & 1) else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


class LocalSentenceTransformerEmbeddings(Embeddings):
    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or os.getenv(
            "EMBEDDING_MODEL",
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        )
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(self.model_name, device="cpu", local_files_only=True)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return vectors.tolist()

    def embed_query(self, text: str) -> list[float]:
        vector = self.model.encode(text, normalize_embeddings=True, show_progress_bar=False)
        return vector.tolist()


def get_embeddings() -> Embeddings:
    config = get_settings()
    return _embeddings(config.embedding_backend, config.embedding_model, config.embedding_revision)


@lru_cache(maxsize=1)
def _embeddings(backend: str, model: str, revision: str) -> Embeddings:
    if backend == "sentence-transformers":
        return LocalSentenceTransformerEmbeddings(model)
    return LocalHashEmbeddings()


def get_vector_store(
    persist_directory: str | Path | None = None,
    collection_name: str | None = None,
    with_embeddings: bool = True,
) -> Chroma:
    persist_path = Path(persist_directory or DEFAULT_VECTOR_DIR)
    persist_path.mkdir(parents=True, exist_ok=True)
    return Chroma(
        collection_name=collection_name or _manifest()["collection"],
        persist_directory=str(persist_path),
        embedding_function=get_embeddings() if with_embeddings else None,
        collection_metadata={"hnsw:num_threads": 1},
        client_settings=Settings(
            is_persistent=True,
            persist_directory=str(persist_path),
            anonymized_telemetry=False,
            chroma_product_telemetry_impl="modules.chroma_telemetry.NoopTelemetry",
        ),
    )


def index_documents(documents: list[Document], source_file: str) -> int:
    if not documents:
        raise ValueError("文档没有可索引片段")
    with STATE_LOCK:
        old = get_vector_store(with_embeddings=False)
        if old.get(limit=1)["ids"]:
            _check_compatible()
        _publish_snapshot(documents, source_file)
    return len(documents)


def _publish_snapshot(documents: list[Document], source: str | None, rebuild: bool = False) -> None:
    """Copy existing vectors, stage new vectors, then atomically publish a pointer.

    Failure leaves the old collection readable. Keep one previous snapshot and
    the original V1 collection; never mutate an active collection in place.
    """
    old_manifest = _manifest()
    name = "rag_snapshot_" + uuid.uuid4().hex
    staged = get_vector_store(collection_name=name, with_embeddings=False)
    try:
        if not rebuild:
            old = get_vector_store(with_embeddings=False).get(include=["documents", "metadatas", "embeddings"])
            keep = [i for i, m in enumerate(old["metadatas"]) if m.get("source") != source]
            for start in range(0, len(keep), 256):
                batch = keep[start:start + 256]
                staged._collection.add(ids=[old["ids"][i] for i in batch],
                    documents=[old["documents"][i] for i in batch],
                    metadatas=[old["metadatas"][i] for i in batch],
                    embeddings=[old["embeddings"][i] for i in batch])
        if documents:
            embedding = get_embeddings()
            for start in range(0, len(documents), 128):
                batch = documents[start:start + 128]
                texts = [d.page_content for d in batch]
                staged._collection.add(ids=[uuid.uuid4().hex for _ in batch], documents=texts,
                    metadatas=[d.metadata for d in batch], embeddings=embedding.embed_documents(texts))
        atomic_json(MANIFEST_PATH, {"collection": name,
            "embedding": embedding_signature() if documents or rebuild else old_manifest["embedding"],
            "previous": old_manifest["collection"]})
    except Exception:
        staged.delete_collection()
        raise
    obsolete = old_manifest.get("previous", "")
    if obsolete.startswith("rag_snapshot_") and obsolete not in {name, old_manifest["collection"]}:
        try:
            get_vector_store(collection_name=obsolete, with_embeddings=False).delete_collection()
        except Exception:
            pass  # Publication succeeded; cleanup may safely be retried later.


def rebuild_index(documents: list[Document]) -> int:
    with STATE_LOCK:
        _publish_snapshot(documents, None, rebuild=True)
    return len(documents)


def retrieve_documents(
    question: str,
    top_k: int = 4,
    search_mode: str = "hybrid",
    candidate_k: int | None = None,
    source_filter: str | None = None,
    rerank: bool | str = True,
) -> list[tuple[Document, float]]:
    readonly_store = get_vector_store(with_embeddings=False)
    if not readonly_store.get(limit=1).get("ids"):
        return []

    candidate_k = max(candidate_k or top_k * 5, top_k)
    search_mode = (search_mode or "hybrid").strip().lower()

    if search_mode == "vector":
        _check_compatible()
        return _vector_search(question, top_k, source_filter)
    if search_mode == "keyword":
        return _keyword_search(question, top_k, source_filter)

    _check_compatible()
    vector_results = _vector_search(question, candidate_k, source_filter)
    keyword_results = _keyword_search(question, candidate_k, source_filter)
    fused = _rrf_fuse([vector_results, keyword_results])
    mode = get_settings().reranker if rerank is True else (rerank if rerank else "none")
    ranked = _semantic_rerank(question, fused) if mode == "semantic" else (_rerank(question, fused) if mode == "lightweight" else fused)
    for document, _ in ranked:
        document.metadata.setdefault("reranker", mode)
    return ranked[:top_k]


def list_indexed_sources() -> list[dict[str, int | str]]:
    store = get_vector_store(with_embeddings=False)
    data = store.get(include=["metadatas"])
    stats: dict[str, dict[str, int | str]] = {}

    for metadata in data.get("metadatas", []):
        if not metadata:
            continue
        source = str(metadata.get("source", "未知文档"))
        item = stats.setdefault(source, {"source": source, "chunks": 0, "pages": 0, "sections": 0})
        item["chunks"] = int(item["chunks"]) + 1
        page = int(metadata.get("page") or 0)
        if page:
            item["pages"] = max(int(item["pages"]), page)
        if str(metadata.get("section") or "").strip():
            item["sections"] = int(item["sections"]) + 1

    return sorted(stats.values(), key=lambda item: str(item["source"]))


def delete_source(source_file: str) -> int:
    with STATE_LOCK:
        data = get_vector_store(with_embeddings=False).get(where={"source": source_file})
        if data["ids"]:
            _publish_snapshot([], source_file)
        return len(data["ids"])


@lru_cache(maxsize=1)
def _cross_encoder(model: str):
    from sentence_transformers import CrossEncoder
    return CrossEncoder(model, device="cpu", local_files_only=True)


def _semantic_rerank(question: str, results: list[tuple[Document, float]]) -> list[tuple[Document, float]]:
    if not results:
        return results
    try:
        scores = _cross_encoder(get_settings().reranker_model).predict(
            [(question, doc.page_content) for doc, _ in results], batch_size=8)
        ranked = []
        for (doc, original), score in zip(results, scores):
            doc.metadata.update(reranker="semantic", retrieval_score=original)
            ranked.append((doc, float(score)))
        return sorted(ranked, key=lambda item: item[1], reverse=True)
    except Exception:
        ranked = _rerank(question, results)
        for doc, _ in ranked:
            doc.metadata.update(reranker="lightweight-fallback", reranker_warning="语义重排模型不可用，已降级轻量重排")
        return ranked


def tokenize(text: str) -> list[str]:
    lowered = text.lower()
    compact = re.sub(r"\s+", "", lowered)
    tokens = re.findall(r"[a-z0-9_]+", lowered)
    tokens.extend(re.findall(r"[\u4e00-\u9fff]", compact))
    tokens.extend(compact[index : index + 2] for index in range(max(len(compact) - 1, 0)))
    return [token for token in tokens if token.strip()]


def _vector_search(question: str, top_k: int, source_filter: str | None = None) -> list[tuple[Document, float]]:
    store = get_vector_store(with_embeddings=True)
    kwargs = {"filter": {"source": source_filter}} if source_filter else {}
    results = store.similarity_search_with_score(question, k=top_k, **kwargs)
    ranked: list[tuple[Document, float]] = []
    for document, distance in results:
        document.metadata = dict(document.metadata or {})
        document.metadata["retrieval_mode"] = "vector"
        ranked.append((document, _distance_to_similarity(distance)))
    return ranked


def _keyword_search(question: str, top_k: int, source_filter: str | None = None) -> list[tuple[Document, float]]:
    documents = _all_documents(source_filter)
    if not documents:
        return []

    scores = _bm25_scores(question, documents)
    ranked = sorted(zip(documents, scores), key=lambda item: item[1], reverse=True)
    best = [(document, round(score, 4)) for document, score in ranked if score > 0][:top_k]
    for document, _ in best:
        document.metadata = dict(document.metadata or {})
        document.metadata["retrieval_mode"] = "keyword"
    return best


def _all_documents(source_filter: str | None = None) -> list[Document]:
    store = get_vector_store(with_embeddings=False)
    kwargs = {"where": {"source": source_filter}} if source_filter else {}
    data = store.get(include=["documents", "metadatas"], **kwargs)
    documents: list[Document] = []
    for content, metadata in zip(data.get("documents", []), data.get("metadatas", [])):
        if content:
            documents.append(Document(page_content=content, metadata=metadata or {}))
    return documents


def _bm25_scores(question: str, documents: list[Document]) -> list[float]:
    query_tokens = tokenize(question)
    tokenized_docs = [tokenize(document.page_content) for document in documents]
    if not query_tokens or not tokenized_docs:
        return [0.0 for _ in documents]

    doc_count = len(tokenized_docs)
    avg_len = sum(len(tokens) for tokens in tokenized_docs) / max(doc_count, 1)
    doc_freq: Counter[str] = Counter()
    for tokens in tokenized_docs:
        doc_freq.update(set(tokens))

    k1 = 1.5
    b = 0.75
    scores: list[float] = []
    for tokens in tokenized_docs:
        frequencies = Counter(tokens)
        doc_len = len(tokens) or 1
        score = 0.0
        for token in query_tokens:
            if token not in frequencies:
                continue
            idf = math.log(1 + (doc_count - doc_freq[token] + 0.5) / (doc_freq[token] + 0.5))
            tf = frequencies[token]
            denominator = tf + k1 * (1 - b + b * doc_len / max(avg_len, 1))
            score += idf * (tf * (k1 + 1)) / denominator
        scores.append(score)

    max_score = max(scores) if scores else 0
    if max_score <= 0:
        return scores
    return [score / max_score for score in scores]


def _rrf_fuse(result_sets: Iterable[list[tuple[Document, float]]]) -> list[tuple[Document, float]]:
    k = 60
    fused_scores: defaultdict[str, float] = defaultdict(float)
    best_documents: dict[str, Document] = {}
    mode_sets: defaultdict[str, set[str]] = defaultdict(set)

    for results in result_sets:
        for rank, (document, score) in enumerate(results, start=1):
            key = _document_key(document)
            fused_scores[key] += 1 / (k + rank)
            mode = str((document.metadata or {}).get("retrieval_mode") or "hybrid")
            mode_sets[key].update(part for part in mode.split("+") if part)
            if key not in best_documents or score > float(best_documents[key].metadata.get("raw_score", 0)):
                metadata = dict(document.metadata or {})
                metadata["raw_score"] = score
                best_documents[key] = Document(page_content=document.page_content, metadata=metadata)

    max_score = max(fused_scores.values()) if fused_scores else 0
    ranked = []
    for key, score in fused_scores.items():
        normalized = score / max_score if max_score else 0.0
        document = best_documents[key]
        document.metadata["retrieval_mode"] = "+".join(sorted(mode_sets[key])) or "hybrid"
        ranked.append((document, round(normalized, 4)))
    return sorted(ranked, key=lambda item: item[1], reverse=True)


def _rerank(question: str, results: list[tuple[Document, float]]) -> list[tuple[Document, float]]:
    query_tokens = set(tokenize(question))
    if not query_tokens:
        return results

    question_compact = re.sub(r"\s+", "", question.lower())
    reranked: list[tuple[Document, float]] = []
    for document, score in results:
        doc_tokens = set(tokenize(document.page_content))
        overlap = len(query_tokens & doc_tokens) / max(len(query_tokens), 1)
        phrase_boost = 0.08 if question_compact and question_compact in re.sub(r"\s+", "", document.page_content.lower()) else 0
        section_boost = 0.04 if str(document.metadata.get("section") or "").strip() else 0
        final_score = min(score * 0.82 + overlap * 0.18 + phrase_boost + section_boost, 1.0)
        document.metadata["rerank_overlap"] = round(overlap, 4)
        reranked.append((document, round(final_score, 4)))
    return sorted(reranked, key=lambda item: item[1], reverse=True)


def _document_key(document: Document) -> str:
    metadata = document.metadata or {}
    return f"{metadata.get('source')}:{metadata.get('chunk_index')}:{metadata.get('char_start')}"


def _distance_to_similarity(distance: float) -> float:
    return round(1 / (1 + max(distance, 0)), 4)
