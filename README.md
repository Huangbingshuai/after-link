# AfterLink 知识工作台

AfterLink 是一个本地优先的知识库导入与问答项目。它把 PDF/Markdown 导入、混合检索和问答整合在统一工作台中，并使用 Docker 管理本地数据服务。

## 功能

- PDF 通过 MinerU 转成 Markdown；Markdown 文件可直接导入。
- BGE-M3 生成稠密与稀疏向量，Milvus 执行混合检索，BGE Reranker 重排结果。
- Neo4j 保存产品、文档和章节关系，并提供章节检索。
- MongoDB 保存会话记录；MinIO 保存导入文件及图片。
- 可选接入 DashScope WebSearch MCP。
- 统一问答工作台同时提供问答与导入入口。

## 项目结构

| 路径 | 用途 |
| --- | --- |
| `app/query_process/` | 问答 API、检索工作流和统一工作台 |
| `app/import_process/` | PDF/Markdown 导入 API 与处理工作流 |
| `app/clients/` | MongoDB、Milvus、Neo4j、MinIO 客户端 |
| `app/lm/` | LLM、嵌入模型与重排模型适配 |
| `prompts/` | 导入和问答提示词 |
| `compose.yaml` | 本地 MongoDB、Milvus、MinIO、etcd 与 Neo4j |
| `.env.example` | 配置模板；复制为 `.env` 后填写本机值 |
| `docs/` | 工作台设计说明和实施计划 |

PDF 手册、模型权重、密钥、日志和导入产物属于本机数据，不纳入 Git。

## 前置要求

- macOS/Linux、Conda、Python 3.11 或更高版本。
- Docker Desktop 或 Docker Engine 与 Docker Compose 插件。
- MinerU API 凭据；使用问答生成时还需要配置所选 LLM 服务商。
- 本地 BGE-M3 与 BGE Reranker 模型目录。模型文件不随仓库分发。
- 可选：DashScope API Key，用于 WebSearch MCP。

Python 依赖与锁定版本见 `pyproject.toml` 和 `uv.lock`。已有 Conda 环境 `after-link` 时，可直接按下方命令启动；新环境请先依据依赖文件安装项目依赖。

## 配置

```bash
cp .env.example .env
```

在 `.env` 中填写模型服务地址和密钥、MinerU Token、BGE 模型路径，以及 Milvus 集合名。`.env.example` 中的 MongoDB、MinIO 和 Neo4j 凭据仅供本机开发使用，部署到其他环境前请替换。不要提交 `.env`。

## 启动

在项目根目录启动本地服务容器：

```bash
docker compose up -d
```

在两个终端分别启动导入 API 和问答 API：

```bash
conda run --no-capture-output -n after-link uvicorn app.import_process.api.file_import_service:app --host 127.0.0.1 --port 8002
```

```bash
conda run --no-capture-output -n after-link uvicorn app.query_process.api.query_service:app --host 127.0.0.1 --port 8003
```

访问地址：

- 统一问答工作台：<http://127.0.0.1:8003/>
- 导入页面：<http://127.0.0.1:8002/import.html>
- 问答健康检查：<http://127.0.0.1:8003/health>
- Neo4j Browser：<http://127.0.0.1:7476/>
- MinIO Console：<http://127.0.0.1:9001/>

停止服务 API 可在对应终端按 `Ctrl+C`。停止容器但保留数据卷：

```bash
docker compose down
```

不要使用 `docker compose down -v`，它会删除本地服务数据卷。

## 检查

```bash
uv lock --check
PYTHONPATH=. python -m unittest discover -s test -p 'test_neo4j_graph.py'
PYTHONPATH=. python -m compileall -q app
```

当前独立回归用例覆盖 Neo4j 同一文档重导入后的章节更新。导入完整 PDF 会调用 MinerU；问答会调用配置的 LLM/WebSearch 服务商，按需测试并留意服务商计费规则。

## 仓库信息

- 仓库：`Huangbingshuai/after-link`
- 可见性：Private
- 默认分支：`main`
- 许可证：未指定；项目未声明开源授权。
