# AfterLink 知识工作台

AfterLink 是一个本地运行的文档知识库与问答应用。导入产品手册后，可以在统一工作台中提问，并通过向量检索、图谱检索和重排查找相关内容。

![AfterLink 工作台：知识问答与文档导入使用同一导航](docs/assets/afterlink-workspace.png)

## 功能

- 在同一工作台切换**知识问答**和**文档导入**。
- 导入 PDF（MinerU 解析）和 Markdown，跟踪后台处理任务。
- 使用 BGE-M3、Milvus 和 BGE Reranker 检索知识库；Neo4j 保存文档图谱。
- 使用 MongoDB 保存会话历史，MinIO 保存导入文件与图片。
- 可选使用 DashScope WebSearch MCP 扩展网络检索。

## 快速开始

从仓库根目录执行以下命令。首次安装依赖、下载模型权重和启动 Milvus 可能需要较多时间与磁盘空间。

### 1. 准备环境

需要 Conda、Python 3.11+、Docker Desktop 或 Docker Engine，以及 Docker Compose 插件。

建议使用新的 Conda 环境。`uv sync` 会根据锁文件同步环境，并可能移除环境中未声明的包；`--active` 指定当前激活的 Conda 环境。

```bash
conda create -n after-link python=3.11 -y
conda activate after-link
python -m pip install uv
uv sync --active --frozen --no-install-project
```

### 2. 配置 `.env`

```bash
cp .env.example .env
```

编辑 `.env`，填写 LLM 服务商密钥与地址、MinerU 凭据、本地 BGE 模型路径，以及下面这些本地数据服务连接项。模型权重不包含在仓库中。

```dotenv
# 与 compose.yaml 的本机开发默认凭据匹配；仅供本机开发
MONGO_ROOT_USERNAME=after_link
MONGO_ROOT_PASSWORD=after_link_mongo_dev
MONGO_URL=mongodb://after_link:after_link_mongo_dev@127.0.0.1:27017/?authSource=admin
MONGO_DB_NAME=after_link

MILVUS_URL=http://127.0.0.1:19530
CHUNKS_COLLECTION=after_link_chunks
ENTITY_NAME_COLLECTION=after_link_entities
ITEM_NAME_COLLECTION=after_link_items

MINIO_ENDPOINT=127.0.0.1:9000
MINIO_ACCESS_KEY=after_link_minio
MINIO_SECRET_KEY=after_link_minio_dev
MINIO_BUCKET_NAME=kb-import-bucket
MINIO_IMG_DIR=images
MINIO_PDF_DIR=pdf_files
MINIO_SECURE=False

NEO4J_URI=bolt://127.0.0.1:7688
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=after_link_neo4j_dev
```

这些凭据与 Compose 本机开发默认值对应。若修改 `.env` 中的 MongoDB、MinIO 或 Neo4j 用户名/密码，也要让 Compose 使用相同的值。不要把真实 API Key、MinerU Token 或 `.env` 提交到 Git。

主要模型和外部 API 配置：

| 变量 | 说明 |
| --- | --- |
| `OPENAI_BASE_URL`、`OPENAI_API_BASE`、`OPENAI_API_KEY` | OpenAI 兼容服务的地址与密钥；两个地址按 `.env.example` 注释保持一致 |
| `LLM_DEFAULT_MODEL`、`LLM_DEFAULT_TEMPERATURE`、`VL_MODEL` | 问答模型、温度和视觉模型 |
| `MINERU_BASE_URL`、`MINERU_API_TOKEN` | PDF 解析；导入 PDF 时必需 |
| `BGE_M3_PATH`、`BGE_M3`、`BGE_DEVICE`、`BGE_FP16` | BGE-M3 本地模型目录与运行参数 |
| `BGE_RERANKER_LARGE`、`BGE_RERANKER_DEVICE`、`BGE_RERANKER_FP16` | BGE Reranker 本地模型目录与运行参数 |
| `DASHSCOPE_API_KEY`、`MCP_DASHSCOPE_BASE_URL` | 可选的 DashScope WebSearch MCP；服务地址见 `.env.example` |

### 3. 启动数据服务

```bash
docker compose up -d
docker compose ps
```

默认端口绑定在本机回环地址：MongoDB `27017`、Milvus `19530`、MinIO API `9000`、MinIO Console `9001`、Neo4j Browser `7476`、Neo4j Bolt `7688`。Compose 还会启动 Milvus 所需的 etcd。

### 4. 启动两个 API

在两个终端分别运行：

```bash
conda activate after-link
uvicorn app.import_process.api.file_import_service:app --host 127.0.0.1 --port 8002
```

```bash
conda activate after-link
uvicorn app.query_process.api.query_service:app --host 127.0.0.1 --port 8003
```

### 5. 打开工作台并验证

- 统一工作台：<http://127.0.0.1:8003/>
- 问答 API 健康检查：<http://127.0.0.1:8003/health>
- 导入页面：<http://127.0.0.1:8002/import.html>
- 问答 API 文档：<http://127.0.0.1:8003/docs>
- 导入 API 文档：<http://127.0.0.1:8002/docs>
- Neo4j Browser：<http://127.0.0.1:7476/>
- MinIO Console：<http://127.0.0.1:9001/>

```bash
curl -fsS http://127.0.0.1:8003/health
```

健康检查只确认问答 API 能响应，不代表数据库、模型或外部服务都可用。查看容器日志：

```bash
docker compose logs -f mongo etcd milvus minio neo4j
```

## API 概览

| 服务 | 方法与路径 | 用途 |
| --- | --- | --- |
| 问答 | `POST /query` | 提交问题；请求可启用流式响应 |
| 问答 | `GET /stream/{session_id}` | 接收流式回答 |
| 问答 | `GET /history/{session_id}` | 查询会话历史 |
| 问答 | `DELETE /history/{session_id}` | 清除会话历史 |
| 导入 | `POST /upload` | 上传一个或多个文件并启动导入任务 |
| 导入 | `GET /status/{task_id}` | 查看导入任务状态 |

## 停止服务

在运行 API 的终端按 `Ctrl+C`。停止容器但保留数据库数据卷：

```bash
docker compose down
```

不要随意使用 `docker compose down -v`，它会删除 Compose 数据卷及其中保存的数据。

## 项目结构

| 路径 | 内容 |
| --- | --- |
| `app/query_process/` | 问答 API、检索工作流和统一工作台 |
| `app/import_process/` | 文档导入 API 和处理工作流 |
| `app/clients/` | MongoDB、Milvus、Neo4j、MinIO 客户端 |
| `app/lm/` | LLM、嵌入模型与重排模型适配 |
| `prompts/` | 导入和问答提示词 |
| `compose.yaml` | 本地数据服务容器配置 |
| `.env.example` | 环境变量模板 |

## 安全与数据

- `.env`、PDF 手册、模型权重、日志和导入产物不纳入仓库。
- Compose 中的开发凭据只适用于本机开发；部署到其他环境前请替换。
- API 当前面向本机开发。对外部署前应配置身份验证并限制跨域来源；上传文件及问答也可能调用外部服务。

## 许可证

[MIT License](LICENSE)
