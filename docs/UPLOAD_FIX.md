# Windows 上传崩溃修复（2026-10-10）

## 原因与修复

本机的最小复现确认了两处 Python 无法捕获的原生访问冲突：

- `onnxruntime 1.31.0` 在导入原生扩展时崩溃。
- `chroma-hnswlib 0.7.6` 在 `Index.add_items()` 时崩溃；NumPy 1.26.4 和 2.0.2 下均复现。普通 API 异常处理不能阻止进程退出。

修复后的项目虚拟环境和 `requirements.txt` 固定为：Chroma 0.5.3、chroma-hnswlib 0.7.3、NumPy 1.26.4、ONNX Runtime 1.19.2。`pip check` 无依赖冲突。此组合在本机通过验证，并非对所有 Windows 环境的保证。

新索引使用一个 HNSW 工作线程。恢复自定义 Noop telemetry，避免旧 Chroma 与新版 posthog 接口不匹配产生重复错误日志。

`scripts/check_runtime.py` 在独立进程中检查依赖版本、ONNX 导入及 HNSW 写入/查询。Windows 启动脚本在启动服务前执行此检查；检查失败时明确停止并提示修复依赖。后端启用 `faulthandler`，后续原生崩溃会留下调用栈。

## 索引恢复原则

原文件和旧索引应保留。若进程在首次构建索引时退出，可能留下尚未发布的快照；应先检查活动指针和原文件，再重建索引。

恢复前停止服务，完整备份数据目录，再通过 `/index/rebuild` 从原文件构建并原子发布新快照。公开文档不记录私人文件内容、正式知识库统计或备份标识。

## 验证结果

- 最终 pytest：**45 passed in 10.11s**。
- 130 页、至少 100 个片段的 PDF：上传、Vector 查询、重新索引、连续上传及健康接口全部通过。
- 独立测试目录中的 PDF 和 Markdown：上传、全库重建、向量查询通过。
- 索引恢复后：新 Python 进程可重新读取持久化索引并完成 Vector 查询。
- `pip check` 与 `git diff --check` 通过。
- 一键脚本启动前后端后：浏览器 HTML 请求返回 200，健康接口返回 `ok`。
- 运行中的 HTTP 服务上传 PDF 返回 200，上传后健康接口仍为 `ok`。公开回归测试使用自动生成的 PDF，不包含私人文档。

这些验证针对上传崩溃修复。远程 LLM、可选语义模型、完整 V2 前端升级没有在本轮作验收结论。

## 启动与重装

本机虚拟环境已修复，日常使用 `start_all.bat`。

其他机器或虚拟环境依赖不一致时，运行 `install_and_start.bat`，或：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -X faulthandler scripts/check_runtime.py
```

上游有类似 HNSW 写入崩溃的报告：[Chroma issue #2992](https://github.com/chroma-core/chroma/issues/2992)。本次原因判断与修复结果以本机复现和测试为依据。
