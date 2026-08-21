# 知源（ZhiYuan）

面向企业内部的个人知识库问答系统。把 PDF、Word、PPT、Excel 和技术文档摄入向量库，用 RAG（检索增强生成）回答问题，回答可追溯到来源文档。

上传文档 → 自动解析、分块、向量化 → 提问时检索相关片段 → 大模型基于上下文流式生成回答。

## 功能

- **文档摄入**：支持 PDF / Word / PPT / Excel / Markdown / 代码文件；SHA-256 去重；失败可重新摄入
- **RAG 问答**：向量检索 + 关键词重排 + 带引用的流式生成（SSE）
- **对话历史**：多会话管理，切换路由不中断流式；按用户隔离，缓存键含 `user_id`
- **角色权限**：站长 / 管理员 / 普通用户三级；首个注册用户自动成为站长；文档增删改仅管理员
- **用户管理**：站长可查看、删除、重置密码、升降角色；管理员只能管理普通用户
- **生产加固**：JWT 鉴权、统一异常、Redis 查询缓存（不可用自动降级）、结构化日志

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI · SQLAlchemy 2 (async) · Pydantic · JWT · bcrypt |
| 前端 | Vue 3 · Vite · Pinia · Vue Router · Tailwind CSS |
| 向量库 | Qdrant |
| 关系库 | PostgreSQL 16 |
| 缓存 | Redis 7 |
| 部署 | Docker Compose（前端 nginx + 后端 + 基础设施） |

LLM 和 Embedding 走 OpenAI 兼容接口，不绑定具体厂商。当前接入 step-3.7-flash（对话）和 qwen3-embedding-8b（向量，768 维）。

## 架构

```
浏览器 ──► nginx (Vue 静态) ──► FastAPI
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
                 Postgres     Qdrant        Redis
                (用户/文档     (向量块)      (查询缓存)
                 /对话)
                    │
                    ▼
              LLM / Embedding API  (OpenAI 兼容)
```

摄入管线：`parse → chunk → embed → Qdrant upsert`，同时在 Postgres 记录文档状态。

查询管线：`embed(question) → Qdrant top-k → 关键词重排 → 拼 prompt → LLM SSE 流式生成`。

## 快速开始

需要：Python 3.12、Node.js 20+、Docker Desktop、[uv](https://docs.astral.sh/uv/)。

### 一键启动（开发）

```bash
cp .env.example .env          # 填写 LLM / Embedding 的 URL 和 key
bash scripts/dev.sh           # Linux / macOS / Git Bash
# 或
.\scripts\dev.ps1             # Windows PowerShell
```

脚本会拉起 Qdrant / Postgres / Redis，再启动后端和前端。

- 前端：http://localhost:5173
- API 文档：http://localhost:8000/docs

### 手动分步

```bash
# 1. 基础设施
docker compose up -d qdrant postgres redis

# 2. 后端
cp .env.example .env
uv sync
uv run uvicorn app.main:app --reload --port 8000

# 3. 前端（另开终端）
cd frontend && npm install && npm run dev
```

### Docker 全栈部署

```bash
cp .env.example .env
docker compose up -d --build
```

访问 http://localhost 。生产环境务必把 `.env` 里的 `ZHIYUAN_JWT_SECRET` 改成随机长字符串。

## 配置

所有环境变量以 `ZHIYUAN_` 为前缀，见 [`.env.example`](.env.example)。必填项：

| 变量 | 说明 |
|---|---|
| `ZHIYUAN_LLM_BASE_URL` / `API_KEY` / `MODEL` | 对话模型（OpenAI 兼容） |
| `ZHIYUAN_EMBEDDING_BASE_URL` / `API_KEY` / `MODEL` | 向量模型 |
| `ZHIYUAN_EMBEDDING_DIM` | 向量维度，须与模型输出一致（qwen3-embedding-8b 为 768） |
| `ZHIYUAN_JWT_SECRET` | JWT 签名密钥，生产环境必须改 |

Langfuse 和 Redis 为可选；未配置时分别降级为 structlog 日志和内存直查。

## 权限模型

| 角色 | 如何获得 | 能做什么 |
|---|---|---|
| 站长 `owner` | 系统第一个注册用户 | 全部管理员能力 + 升降其他用户角色 |
| 管理员 `admin` | 站长提升 | 上传 / 删除 / 重新摄入文档；管理普通用户 |
| 普通用户 `user` | 后续注册 | 问答、查看自己的对话历史 |

管理员不能操作其他管理员或站长。站长角色不可被修改或删除。

## 项目结构

```
app/
  api/            鉴权、问答、文档、对话、用户管理
  auth/           JWT、密码、依赖注入
  ingestion/      解析 / 分块 / 摄入管线
  rag/            检索编排、prompt 构建
  retrieval/      向量检索、关键词重排
  storage/        Postgres 模型、Qdrant 客户端
  llm/            OpenAI 兼容 LLM 客户端
  embedding/      OpenAI 兼容 Embedding 客户端
frontend/         Vue 3 单页应用
scripts/          开发启动脚本
tests/            pytest（42+）
```

## 测试

```bash
uv run pytest tests/ -q
```
