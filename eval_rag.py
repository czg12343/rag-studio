"""Deterministic source-level retrieval evaluation; never invokes an LLM."""
from __future__ import annotations
import argparse
import json
import math
import os
import tempfile
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent
DEFAULT_EVAL_FILE = ROOT / 'data' / 'eval_questions.json'


def retrieval_metrics(ranked: list[str], relevant: list[str], k: int) -> dict:
    relevant_set = {item for item in relevant if item.strip()}
    if not relevant_set:
        return {'recall_at_k': None, 'mrr': None, 'ndcg_at_k': None}
    unique = list(dict.fromkeys(ranked))[:k]
    gains = [int(source in relevant_set) for source in unique]
    recall = sum(gains) / len(relevant_set)
    mrr = next((1 / (i + 1) for i, hit in enumerate(gains) if hit), 0.0)
    dcg = sum(hit / math.log2(i + 2) for i, hit in enumerate(gains))
    ideal = sum(1 / math.log2(i + 2) for i in range(min(k, len(relevant_set))))
    return {'recall_at_k': recall, 'mrr': mrr, 'ndcg_at_k': dcg / ideal}


def _answer_point_hit_rate(answer: str, expected_points: list[str]) -> float | None:
    points = [point.strip() for point in expected_points if point.strip()]
    if not points:
        return None
    return sum(point in answer for point in points) / len(points)


def _evaluate_case(case: dict, top_k: int, search_mode: str, reranker: str = 'none') -> dict:
    from modules.vector_store import retrieve_documents
    retrieved = retrieve_documents(case['question'], top_k=top_k, candidate_k=max(20, top_k),
                                   search_mode=search_mode, rerank=reranker)
    sources = [doc.metadata['source'] for doc, _ in retrieved]
    return {'question': case['question'], 'top_sources': sources,
            **retrieval_metrics(sources, case.get('expected_sources', []), top_k),
            'rerankers_used': sorted({doc.metadata.get('reranker', 'none') for doc, _ in retrieved})}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', default=str(DEFAULT_EVAL_FILE))
    parser.add_argument('--top-k', type=int, default=3)
    parser.add_argument('--mode', choices=['vector', 'keyword', 'hybrid'], default='hybrid')
    parser.add_argument('--all', action='store_true', help='Compare vector, BM25, hybrid and hybrid + lightweight reranker')
    parser.add_argument('--sample', action='store_true', help='Use checked-in corpus in an isolated temporary index')
    parser.add_argument('--reranker', choices=['none', 'lightweight', 'semantic'], default='none')
    parser.add_argument('--output')
    args = parser.parse_args()
    if not 1 <= args.top_k <= 20:
        parser.error('top-k must be 1..20')
    if args.sample:
        os.environ['RAG_DATA_DIR'] = tempfile.mkdtemp(prefix='rag-eval-')
        os.environ['EMBEDDING_BACKEND'] = 'hash'
    from modules.settings import Settings, save_settings, embedding_signature
    from modules.vector_store import rebuild_index
    from modules.text_splitter import split_text
    from modules.document_loader import load_document
    if args.sample:
        save_settings(Settings())
        docs = []
        for path in sorted((ROOT / 'examples' / 'corpus').glob('*.md')):
            loaded = load_document(path)
            docs.extend(split_text(loaded.text, path.name))
        rebuild_index(docs)
    cases = json.loads(Path(args.file).read_text(encoding='utf-8'))
    if not cases:
        parser.error('evaluation file is empty')
    variants = [('vector', 'none'), ('keyword', 'none'), ('hybrid', 'none'), ('hybrid', 'lightweight')] if args.all else [(args.mode, args.reranker)]
    report = {'embedding': embedding_signature(), 'top_k': args.top_k,
              'unit': 'exact source filename; duplicate sources removed within top-K chunks',
              'answer_faithfulness': 'not evaluated: no grounded answer adjudication', 'variants': {}}
    for mode, reranker in variants:
        results = [_evaluate_case(case, args.top_k, mode, reranker) for case in cases]
        metrics = {}
        for key in ('recall_at_k', 'mrr', 'ndcg_at_k'):
            values = [row[key] for row in results if row[key] is not None]
            metrics[key] = mean(values) if values else None
        report['variants'][f'{mode}+{reranker}'] = {'metrics': metrics, 'labeled_cases': sum(row['mrr'] is not None for row in results), 'results': results}
    output = json.dumps(report, ensure_ascii=False, indent=2)
    print(output)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(output + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
