# Atlas 模型与索引
Hash Embedding 是可离线运行的演示算法，不具有预训练语义理解能力。语义 Embedding 可选 multilingual MiniLM，必须提前准备本地模型文件，不自动联网下载。

# 模型切换
索引记录 Embedding 后端、模型名称和版本。模型变化后向量检索要求全库重建，BM25 仍可使用。新索引构建完成才切换活动指针，失败保留旧快照。
