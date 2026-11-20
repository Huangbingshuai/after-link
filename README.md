# AfterLink · 掌柜智库

AfterLink 是面向**产品手册**的本地知识工作台，不是通用聊天机器人。它将 PDF/Markdown 手册整理成带产品名和章节信息的知识切片；问答时先识别并确认产品型号，再从手册和可选的网络搜索中检索依据，最后由配置的大模型组织回答。

![掌柜智库工作台：侧栏可在知识问答和文档导入之间切换](docs/assets/afterlink-workspace.png)

## 系统做什么

### 手册如何进入知识库

```mermaid
flowchart LR
    A[PDF] --> B[MinerU 解析为 Markdown]
    C[Markdown] --> D[读取正文与本地图片]
    B --> D
    D --> E[图片摘要与 MinIO 图片链接]
    E --> F[按标题切分章节]
    F --> G[LLM 识别产品名称]
    G --> H[BGE-M3 生成稠密与稀疏向量]
    H --> I[Milvus 保存产品索引与文本切片]
    I --> J[Neo4j 建立产品、文档、切片关系]
```

- PDF 通过 MinerU 接口解析；Markdown 直接进入后续处理。导入 API 将上传文件暂存在 `output/日期/任务ID/`，并在后台按节点执行流程。
- 文档按 Markdown 标题切分；过长章节会继续拆分，同一父章节内过短的相邻块会合并。
- 如果文档引用了本地图片，系统会尝试调用视觉模型生成摘要，把图片上传到 MinIO，并将 Markdown 中的图片链接替换为 MinIO 地址。
- LLM 从切片中识别产品名称。BGE-M3 为产品名称和正文切片生成稠密、稀疏向量，分别用于产品匹配与混合检索。
- Milvus 保存向量和切片元数据；Neo4j 保存 `Product → Document → Chunk` 关系以及章节、正文和产品信息。

### 问题如何变成回答

```mermaid
flowchart LR
    A[问题与最近会话] --> B[LLM 提取产品名并改写问题]
    B --> C[Milvus 匹配已导入的产品名]
    C -->|型号明确| D[直接问题混合检索]
    C -->|存在候选| E[请用户确认型号]
    C -->|没有候选| F[提示未找到产品]
    D --> G[HyDE 混合检索]
    D --> H[Neo4j 章节词项检索]
    D --> I[可选 DashScope WebSearch]
    G --> J[本地结果 RRF 融合]
    H --> J
    J --> K[合并网络结果并用 BGE Reranker 重排]
    I --> K
    K --> L[大模型生成回答]
    L --> M[SSE 流式输出并写入 MongoDB 会话历史]
```

问答面向已导入的产品手册：系统会结合最近会话抽取产品名并改写追问，再到 `ITEM_NAME_COLLECTION` 中匹配产品。高置信度匹配会自动确认；有候选但不足以直接确认时会请求用户选择；没有候选时会提示补充准确型号。它不会把未匹配的问题当成开放域聊天问题直接回答。产品名向量存于 `ITEM_NAME_COLLECTION`；配置模板中的 `ENTITY_NAME_COLLECTION` 目前是预留字段。

型号确认后，工作流并行执行普通 Milvus 混合检索、HyDE（先生成假设性文档，再检索）和 Neo4j 检索；配置 DashScope 后还会并行调用 WebSearch。普通检索、HyDE 与 Neo4j 结果先做 RRF 融合，随后本地结果和网络摘要一起交给 BGE Reranker，再将选出的上下文交给大模型。问答支持 SSE 流式输出，会话历史存于 MongoDB。

## 能力边界

- Neo4j 已参与文档图谱写入和问答检索。当前检索方式是按查询词与活动 `Chunk` 的正文、章节标题做词项重合匹配，并可按产品名过滤；它不是任意 Cypher 查询，也不提供通用的多跳关系推理。
- 问答结果取决于手册解析质量、产品名识别、模型和检索结果。`/health` 只说明问答 API 可以响应，不代表模型、数据库或外部服务均已就绪。
- 重导入时，Milvus 当前会按识别出的 `item_name` 从文本切片集合删除该产品已有的全部记录，再写入本次切片。同一产品若有多份独立手册，重导入其中一份会替换该产品在 Milvus 中的旧切片；先备份数据并确认这一行为符合预期。Neo4j 则按文档标识更新图谱节点，并把该文档的旧切片标记为非活动。

## 快速开始

以下步骤从仓库根目录执行。需要 macOS/Linux、Conda、Python 3.11+、Docker Desktop 或 Docker Engine，以及 Docker Compose 插件。BGE-M3 和 BGE Reranker 权重不随仓库提供；模型加载、首次向量化和 Milvus 容器启动可能需要较多时间与磁盘空间。

### 1. 创建 Python 环境

建议使用新 Conda 环境。`uv sync` 按 `uv.lock` 同步依赖；它可能移除当前环境中未声明的包。

```bash
conda create -n after-link python=3.11 -y
conda activate after-link
python -m pip install uv
uv sync --active --frozen --no-install-project
```

### 2. 准备配置

```bash
cp .env.example .env
```

在 `.env` 中填写 LLM 服务的 `OPENAI_BASE_URL`、`OPENAI_API_KEY` 和 `LLM_DEFAULT_TEMPERATURE`。`OPENAI_BASE_URL` 是当前客户端实际读取的地址；`.env.example` 中的 `OPENAI_API_BASE` 是保留的兼容字段。若导入含图片的手册，还需配置视觉模型 `VL_MODEL`；导入 PDF 需配置 MinerU 的 `MINERU_BASE_URL` 和 `MINERU_API_TOKEN`。

为模型路径填写你本机的实际目录：

```dotenv
BGE_M3_PATH=/本机路径/bge-m3
BGE_DEVICE=cpu
BGE_FP16=0
BGE_RERANKER_LARGE=/本机路径/bge-reranker-large
BGE_RERANKER_DEVICE=cpu
BGE_RERANKER_FP16=0
```

若 `BGE_M3_PATH` 留空，代码会尝试加载并下载 `BAAI/bge-m3`；Reranker 则需要提供 `BGE_RERANKER_LARGE`。设备参数按实际硬件调整。

本地 Compose 数据服务的连接值示例：

```dotenv
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

这些是与 `compose.yaml` 本机开发默认值对应的示例。改了 MongoDB、MinIO 或 Neo4j 的密码后，要让 `.env` 和 Compose 使用同一组凭据。Milvus 集合名用于本项目首次创建的空集合；连接已有 Milvus 数据时，先填写现有集合名，不要直接复用示例名。

DashScope WebSearch 是可选项：设置 `DASHSCOPE_API_KEY`，并使用 `.env.example` 中的 `MCP_DASHSCOPE_BASE_URL`。未配置时该检索分支会跳过。

### 3. 启动本地数据服务

```bash
docker compose up -d
docker compose ps
```

### 4. 启动两个 API

统一工作台把两种前端入口放在同一页面中，但底层仍是两个独立的 FastAPI 进程：问答 API 在 `8003`，导入 API 在 `8002`。分别在两个终端运行：

```bash
conda activate after-link
uvicorn app.import_process.api.file_import_service:app --host 127.0.0.1 --port 8002
```

```bash
conda activate after-link
uvicorn app.query_process.api.query_service:app --host 127.0.0.1 --port 8003
```

### 5. 访问和检查

| 用途 | 地址 |
| --- | --- |
| 统一工作台（问答与导入） | <http://127.0.0.1:8003/> |
| 问答健康检查 | <http://127.0.0.1:8003/health> |
| 问答 API 文档 | <http://127.0.0.1:8003/docs> |
| 导入 API 文档 | <http://127.0.0.1:8002/docs> |
| Neo4j Browser | <http://127.0.0.1:7476/> |
| MinIO Console | <http://127.0.0.1:9001/> |

导入页面由统一工作台侧栏切换，不需要再单独打开旧页面。健康检查可用下面的命令查看：

```bash
curl -fsS http://127.0.0.1:8003/health
```

## 接口速查

| 服务 | 方法与路径 | 用途 |
| --- | --- | --- |
| 问答 | `POST /query` | 提问；可选择流式响应 |
| 问答 | `GET /stream/{session_id}` | 接收 SSE 流式事件 |
| 问答 | `GET /history/{session_id}` | 查询 MongoDB 会话历史 |
| 问答 | `DELETE /history/{session_id}` | 删除该会话历史 |
| 导入 | `POST /upload` | 以 multipart 字段 `files` 上传 PDF/Markdown |
| 导入 | `GET /status/{task_id}` | 查询任务状态和已完成节点 |

## 日志、停止与数据

查看数据服务日志：

```bash
docker compose logs -f mongo etcd milvus minio neo4j
```

在各 API 终端按 `Ctrl+C` 停止进程。停止容器但保留数据库数据卷：

```bash
docker compose down
```

不要随意执行 `docker compose down -v`，它会删除 Compose 数据卷及其中保存的 MongoDB、Milvus、MinIO 和 Neo4j 数据。导入文件和解析产物保存在本机 `output/`，运行日志保存在 `logs/`；这些路径已从 Git 排除。

## 项目结构

| 路径 | 作用 |
| --- | --- |
| `app/query_process/api/` | 问答 API；根路径提供统一工作台 |
| `app/query_process/agent/` | 产品识别、并行检索、融合重排和回答生成工作流 |
| `app/query_process/page/workspace.html` | 问答/导入共用的工作台前端 |
| `app/import_process/api/` | 文件上传、后台任务启动与状态查询 |
| `app/import_process/agent/` | MinerU 解析、图片处理、切分、向量化和数据入库工作流 |
| `app/clients/` | MongoDB、Milvus、Neo4j、MinIO 客户端 |
| `app/lm/` | LLM、BGE-M3 嵌入与 BGE Reranker 适配 |
| `prompts/` | 产品识别、查询改写、HyDE 与答案提示词 |
| `compose.yaml` | MongoDB、Milvus、MinIO、etcd、Neo4j 本地容器 |
| `.env.example` | 环境变量模板 |

## 数据流与安全说明

- PDF 内容会发送到配置的 MinerU 服务解析；图片摘要会发送到配置的视觉模型；问答问题、必要的会话上下文和检索片段会发送到配置的大模型。启用 DashScope 后，改写后的问题还会发送到 WebSearch 服务。使用前应确认对应服务商的数据政策和计费方式。
- Compose 的主机端口绑定在 `127.0.0.1`。当前 API 没有身份验证，并允许宽泛的跨域访问，适用于本机开发；对外部署前必须补充访问控制并限制 CORS 来源。
- MinIO 客户端会将导入桶设置为匿名只读，以便前端显示手册图片。不要把含敏感资料的该配置直接暴露到公网。
- 本地 Compose 凭据只用于开发。`.env`、密钥、PDF 手册和模型权重不提交到仓库。

## 许可证

[MIT License](LICENSE)
