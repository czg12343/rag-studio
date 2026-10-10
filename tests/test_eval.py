from eval_rag import retrieval_metrics, _answer_point_hit_rate
import pytest


def test_empty_annotations_not_correct():
    assert _answer_point_hit_rate('anything', []) is None
    assert _answer_point_hit_rate('anything', [' ']) is None
    assert retrieval_metrics(['a'], [], 3)['mrr'] is None


def test_metrics_known_ranking():
    result = retrieval_metrics(['wrong', 'a', 'a', 'b'], ['a', 'b'], 3)
    assert result['recall_at_k'] == 1
    assert result['mrr'] == 0.5
    assert result['ndcg_at_k'] == pytest.approx(0.6934264036)
