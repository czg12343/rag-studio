# Atlas 检索策略
Vector Search 使用向量相似度；BM25 Keyword Search 计算词项相关性；Hybrid Search 使用 RRF 融合两路候选。RRF 的排名常数为 60。

# Reranking
The lightweight reranker combines token overlap and retrieval scores. The optional semantic cross encoder runs on CPU. When its local model is unavailable, it falls back to the lightweight reranker.
