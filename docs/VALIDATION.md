# 验证记录

记录日期：2026-10-10。以下结论来自实际执行结果，覆盖当前源码；不代表所有 V2 规划均已完成。

## 环境

- Windows；Python 3.11.7，项目 `.venv`。
- 本次前端构建使用 Node.js 16.20.2、npm 8.19.4；README 和启动脚本提示安装 Node.js 20+，该版本未在本轮重新验证。
- 原生依赖：Chroma 0.5.3、chroma-hnswlib 0.7.3、NumPy 1.26.4、ONNX Runtime 1.19.2。

## 执行结果

| 检查 | 实际结果 |
| --- | --- |
| 后端 `python -m pytest -q` | **45 passed in 12.86s**；使用隔离测试目录，不操作正式知识库 |
| `python -m pip check` | No broken requirements found |
| 前端 `npm run build` | TypeScript 检查与 Vite 构建成功，1582 个模块，11.11s；存在单个 JS 产物超过 500 kB 的提示 |
| `git diff --check` | 通过；Git 提示 Windows 换行转换，没有空白错误 |
| 忽略规则检查 | 16 类私有路径均被忽略，6 个公开样例 / 占位文件保留；没有已跟踪的私有运行文件 |
| 公开来源评测 | 6 份公开文档、12 条标注、Top-K=3、Hash Embedding；结果保存在 [evaluation.json](evaluation.json) |

前端第一次构建因执行沙箱阻止 `realpath` 返回 EPERM；在正常本机权限下重新构建成功。该错误未通过修改业务代码规避。

### 检索评测

| 模式 | Recall@3 | MRR | nDCG@3 | 有效标注数 |
| --- | --- | --- | --- | --- |
| Vector | 1.0000 | 1.0000 | 1.0000 | 12 |
| BM25 | 1.0000 | 1.0000 | 1.0000 | 12 |
| Hybrid | 1.0000 | 1.0000 | 1.0000 | 12 |
| Hybrid + Lightweight Reranker | 1.0000 | 1.0000 | 1.0000 | 12 |

以上数值来自实际脚本输出。样例规模小、问题与文档词汇高度重合，四种方法都达到满分，无法证明混合检索或重排优于其他方法，也不能外推到私人知识库或语义模型。评测不调用 LLM，未计算答案忠实性。

复现命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe eval_rag.py --sample --all --top-k 3 --output docs/evaluation.json
cd frontend
npm run build
```

## 已有上传修复验证

上传修复期间已完成原生 HNSW 写入 / 查询检查、生成的 130 页 PDF 上传与重新索引、运行中 HTTP 上传、健康检查及持久化索引重读。该过程详见 [UPLOAD_FIX.md](UPLOAD_FIX.md)，不公开用户文档、备份标识或知识库统计。

## 尚未验证或尚未完成

- 可选语义 Embedding、Cross Encoder 的实际本地权重与性能；未下载权重。不可用与降级路径有测试，不能代替模型实测。
- 真实远程 LLM 连接、回答忠实性与提供方兼容性；异常路径使用测试替身验证。
- 全新电脑从零安装、Node.js 20+ 构建、Linux / macOS 运行。
- 前端仍以 `App.vue` 为主，多会话聊天、Markdown 渲染、完整检索设置编辑器及独立概览页面尚未完成。对应会话、设置和概览后端接口已实现。
- 手机 / 平板视觉验收、真实截图、大型语料、并发和公网部署。

## 发布与隐私

源代码保留核心业务、兼容界面、启动器、依赖锁文件、测试与公开示例。忽略本地密钥、数据库、上传文件、索引、备份、日志、模型目录和编辑器配置；未删除本地知识库。

`scripts/prepare_release.py` 从明确的文件白名单生成源码包，不导出 `.git` 或提交作者信息。已有 Git 提交历史保留在本机；若直接推送它，作者元数据仍会公开。发布前仍需人工确认自己新增的文档、截图和样例可以公开。
