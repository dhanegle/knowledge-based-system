# 知源 ZhiYuan

<p align="center">
  <a href="https://github.com/dhanegle/knowledge-based-system-zhiyuan/actions/workflows/ci.yml"><img src="https://github.com/dhanegle/knowledge-based-system-zhiyuan/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.12-blue" alt="Python">
  <img src="https://img.shields.io/badge/vue-3-42B883" alt="Vue 3">
  <img src="https://img.shields.io/badge/deploy-docker%20compose-2496ED" alt="Docker Compose">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
</p>

[中文](#知源) · [English](#zhiyuan)

企业知识库问答系统。办公文档与技术资料经摄入进入向量库；提问时用检索增强生成（RAG）作答，回答基于已上传的原文。

An internal knowledge-base Q&A system. Office documents and technical files are ingested into a vector store; questions are answered with retrieval-augmented generation (RAG), grounded in the uploaded sources.


## 知源

上传文档、提问，回答从这些材料里流式生成。文件落在你自己的 Postgres 与 Qdrant 里。发给大模型的只有问题和检索到的片段。

**状态：** 全栈一条 Docker Compose 起齐——前端、API、Qdrant、Postgres、Redis，自托管设计。测试 60 项通过。

### 为什么做知源

多数 RAG 演示停在「传个 PDF 再聊天」。知源按小型内部产品来做：账号、角色、对话不串用户、文档生命周期、一条 Compose 就能起全栈。

| 知识问答 | 运维侧 |
|---|---|
| PDF / Word / PPT / Excel / Markdown / 源码 | JWT；第一个注册的人是站长 |
| 解析 → 分块 → 向量化 → Qdrant | 管理员改知识库；普通用户只问答 |
| 稠密检索 + 关键词重排 + SSE 生成 | 按用户隔离对话；缓存键含 `user_id` |
| Vue 3 界面，Markdown 回答 | Redis 挂了自动跳过缓存 |

### 能力

- **摄入管线** — SHA-256 去重，状态机（`pending` → `indexed` / `failed`），失败或更新后可重新摄入。
- **流式 RAG** — SSE；生成逻辑在 Pinia store，切路由不断流。
- **隔离** — 对话与查询缓存按用户划分。换账号会清前端状态。
- **角色** — `owner` / `admin` / `user`。站长可升降级。管理员不能动其他管理员和站长。
- **OpenAI 兼容接口** — LLM 与 Embedding 的 URL 写在配置里。默认配置开箱即用：step-3.7-flash、qwen3-embedding-8b（768 维），换供应商只改 `.env`。
- **LangChain 双后端** — LLM 与 Embedding 各有原生直连与 LangChain（ChatOpenAI / OpenAIEmbeddings）两套实现，`ZHIYUAN_LLM_BACKEND` / `ZHIYUAN_EMBEDDING_BACKEND` 一键切换，行为等价、随时回退；生成段可走 LCEL 链并接入 Langfuse 整链追踪。
- **Compose 部署** — nginx SPA + FastAPI + Qdrant + Postgres 16 + Redis 7。

### 架构

```
浏览器 ──► nginx（Vue 3 SPA）──► FastAPI
                                  │
                     ┌────────────┼────────────┐
                     ▼            ▼            ▼
                  Postgres     Qdrant        Redis
                 （用户、       （分块）      （查询缓存）
                  文档、
                  对话）
                     │
                     ▼
               LLM / Embedding（OpenAI 兼容 HTTP）
```

**摄入：** `解析 → 分块 → 向量化 → 写入 Qdrant`，Postgres 记文档行。

**提问：** `问题向量化 → Qdrant top-k → 关键词重排 → 拼 prompt → LLM SSE`（LangChain 后端时生成段为 LCEL 链）。

### 技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI、SQLAlchemy 2（async）、Pydantic、JWT、bcrypt、LangChain（可选） |
| 前端 | Vue 3、Vite、Pinia、Vue Router、Tailwind CSS、marked |
| 向量库 | Qdrant 1.12 |
| 数据库 | PostgreSQL 16 |
| 缓存 | Redis 7 |
| 部署 | Docker Compose |

Python `>=3.12,<3.14`。包管理：[uv](https://docs.astral.sh/uv/)。

### 快速开始

**环境：** Python 3.12、Node.js 20+、Docker Desktop、uv。

```bash
git clone https://github.com/dhanegle/knowledge-based-system-zhiyuan.git
cd knowledge-based-system-zhiyuan
cp .env.example .env          # 填写 LLM / Embedding 的 URL、密钥、模型名
bash scripts/dev.sh           # Linux / macOS / Git Bash
# 或
.\scripts\dev.ps1             # Windows PowerShell
```

- 界面：http://localhost:5173
- 接口文档：http://localhost:8000/docs

第一个注册的账号是**站长**。

**分步**

```bash
docker compose up -d qdrant postgres redis
cp .env.example .env && uv sync
uv run uvicorn app.main:app --reload --port 8000
# 另开终端
cd frontend && npm install && npm run dev
```

**全栈 Docker**

```bash
cp .env.example .env
docker compose up -d --build
```

打开 http://localhost。生产环境务必把 `ZHIYUAN_JWT_SECRET` 改成长随机串。

### 配置

前缀 `ZHIYUAN_`。完整列表见 [`.env.example`](.env.example)。

| 变量 | 用途 |
|---|---|
| `ZHIYUAN_LLM_BASE_URL` / `API_KEY` / `MODEL` | 对话（OpenAI 兼容） |
| `ZHIYUAN_EMBEDDING_BASE_URL` / `API_KEY` / `MODEL` | 向量 |
| `ZHIYUAN_EMBEDDING_DIM` | 必须与模型一致（qwen3-embedding-8b 为 768） |
| `ZHIYUAN_LLM_BACKEND` / `ZHIYUAN_EMBEDDING_BACKEND` | `native`（默认，SDK 直连）或 `langchain`，两套实现行为等价 |
| `ZHIYUAN_JWT_SECRET` | 签名密钥；生产必须改 |

Langfuse、Redis 可选。Langfuse 留空则只用 structlog；配置齐全且 LLM 后端为 `langchain` 时，RAG 整链自动上报 trace。Redis 不可用则跳过缓存。

### 角色

| 角色 | 来源 | 权限 |
|---|---|---|
| 站长 owner | 第一个注册 | 全部，含升降级 |
| 管理员 admin | 站长提升 | 改文档；管普通用户 |
| 普通用户 user | 之后注册 | 提问；只看自己的历史 |

管理员不能操作其他管理员和站长。站长不能被删、不能被降级。

### 目录

```
app/
  api/            鉴权、问答、文档、对话、用户管理
  auth/           JWT、密码、FastAPI 依赖
  ingestion/      解析、分块、摄入管线
  rag/            编排、prompt
  retrieval/      向量检索、关键词重排、LangChain Retriever
  storage/        Postgres 模型、Qdrant 客户端
  llm/            OpenAI 兼容对话客户端
  embedding/      OpenAI 兼容向量客户端
frontend/         Vue 3 前端
scripts/          开发启动脚本
tests/            pytest
```

### 验证

```bash
uv run pytest tests/ -q
cd frontend && npm run build
```

不要提交 `.env` 和 API 密钥。

### 安全与隐私

文档和对话存在你的 Postgres / Qdrant。对话与向量请求会把问题和检索片段发给你配置的供应商。漏洞请走 GitHub Issues，不要贴密钥或内部文档。

### 贡献 / Contributing

欢迎 Issue 与 PR，提交前请读 [CONTRIBUTING.md](CONTRIBUTING.md)。

### License / 许可证

[MIT](LICENSE)

---

## ZhiYuan

Upload a document, ask a question, get a streamed answer drawn from that material. Files stay in your own Postgres and Qdrant instance. Only the question and the retrieved excerpts go to the LLM you configure.

**Status:** full stack ships as one Docker Compose file — SPA, API, Qdrant, Postgres, Redis. Self-hosted by design. 60 tests passing.

### Why ZhiYuan

Most RAG demos stop at “upload a PDF and chat.” ZhiYuan is meant to look like a small internal product: accounts, roles, conversation history that does not leak across users, document lifecycle, and a deploy path that is one Compose file.

| Knowledge Q&A | Operations |
|---|---|
| PDF, Word, PPT, Excel, Markdown, source files | JWT accounts; first registrant is owner |
| Parse → chunk → embed → Qdrant | Admins ingest and delete; users only ask |
| Dense retrieve + keyword rerank + SSE generation | Per-user conversations; cache keyed by `user_id` |
| Markdown answers in a Vue 3 UI | Redis cache degrades if Redis is down |

### Highlights

- **Ingestion pipeline** — SHA-256 dedup, status machine (`pending` → `indexed` / `failed`), re-ingest of a failed or updated file.
- **Streaming RAG** — SSE tokens; generation lives in a Pinia store so changing routes does not abort the stream.
- **Isolation** — Conversations and query cache are scoped to the user. Switching accounts clears client state.
- **Roles** — `owner` / `admin` / `user`. Owner can promote and demote. Admins cannot act on other admins or the owner.
- **OpenAI-compatible providers** — LLM and embedding URLs are config, not code. Ships configured for step-3.7-flash and qwen3-embedding-8b (768-d) out of the box.
- **Dual backends** — LLM and embedding each ship as a native implementation plus a LangChain adapter (ChatOpenAI / OpenAIEmbeddings); one env var switches them, behavior-identical and instantly revertible. Generation can run as an LCEL chain with full-chain Langfuse tracing.
- **Compose deploy** — nginx SPA + FastAPI + Qdrant + Postgres 16 + Redis 7.

### Architecture

```
Browser ──► nginx (Vue 3 SPA) ──► FastAPI
                                   │
                      ┌────────────┼────────────┐
                      ▼            ▼            ▼
                   Postgres     Qdrant        Redis
                  (users,       (chunks)      (query cache)
                   docs,
                   chats)
                      │
                      ▼
                LLM / Embedding  (OpenAI-compatible HTTP)
```

**Ingest:** `parse → chunk → embed → Qdrant upsert`, document row in Postgres.

**Ask:** `embed(question) → Qdrant top-k → keyword rerank → prompt → LLM SSE` (LCEL chain for generation when the LangChain backend is on).

### Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI, SQLAlchemy 2 (async), Pydantic, JWT, bcrypt, LangChain (optional) |
| Frontend | Vue 3, Vite, Pinia, Vue Router, Tailwind CSS, marked |
| Vectors | Qdrant 1.12 |
| Database | PostgreSQL 16 |
| Cache | Redis 7 |
| Deploy | Docker Compose |

Python `>=3.12,<3.14`. Package manager: [uv](https://docs.astral.sh/uv/).

### Quick start

**Prerequisites:** Python 3.12, Node.js 20+, Docker Desktop, uv.

```bash
git clone https://github.com/dhanegle/knowledge-based-system-zhiyuan.git
cd knowledge-based-system-zhiyuan
cp .env.example .env          # set LLM and embedding URL / key / model
bash scripts/dev.sh           # Linux / macOS / Git Bash
# or
.\scripts\dev.ps1             # Windows PowerShell
```

- UI: http://localhost:5173
- API docs: http://localhost:8000/docs

The first account you register becomes **owner**.

**Manual**

```bash
docker compose up -d qdrant postgres redis
cp .env.example .env && uv sync
uv run uvicorn app.main:app --reload --port 8000
# other terminal
cd frontend && npm install && npm run dev
```

**Full stack**

```bash
cp .env.example .env
docker compose up -d --build
```

Open http://localhost. In production, set `ZHIYUAN_JWT_SECRET` to a long random string.

### Configuration

Prefix: `ZHIYUAN_`. Full list: [`.env.example`](.env.example).

| Variable | Role |
|---|---|
| `ZHIYUAN_LLM_BASE_URL` / `API_KEY` / `MODEL` | Chat (OpenAI-compatible) |
| `ZHIYUAN_EMBEDDING_BASE_URL` / `API_KEY` / `MODEL` | Embeddings |
| `ZHIYUAN_EMBEDDING_DIM` | Must match the model (768 for qwen3-embedding-8b) |
| `ZHIYUAN_LLM_BACKEND` / `ZHIYUAN_EMBEDDING_BACKEND` | `native` (default, direct SDK) or `langchain`; both implementations behave identically |
| `ZHIYUAN_JWT_SECRET` | Signing key; change in production |

Langfuse and Redis are optional. Empty Langfuse → structlog only; with Langfuse keys set and the LangChain LLM backend enabled, the whole RAG chain is traced automatically. Redis down → queries skip cache.

### Roles

| Role | How | Can |
|---|---|---|
| Owner | First registration | Everything, including promote / demote |
| Admin | Promoted by owner | Mutate documents; manage regular users |
| User | Later registrations | Ask; own history only |

Admins cannot target other admins or the owner. Owner cannot be deleted or demoted.

### Layout

```
app/
  api/            Auth, Q&A, documents, conversations, admin users
  auth/           JWT, passwords, FastAPI dependencies
  ingestion/      Parsers, chunker, pipeline
  rag/            Orchestration, prompts
  retrieval/      Vector search, keyword rerank, LangChain Retriever
  storage/        Postgres models, Qdrant client
  llm/            OpenAI-compatible chat client
  embedding/      OpenAI-compatible embedding client
frontend/         Vue 3 SPA
scripts/          Dev launchers
tests/            pytest
```

### Verification

```bash
uv run pytest tests/ -q
cd frontend && npm run build
```

Do not commit `.env` or API keys.

### Security and privacy

Documents and conversations stay in your Postgres / Qdrant. Chat and embedding calls send the question and retrieved excerpts to the provider you configured. Report issues in GitHub Issues; do not paste keys or private documents.

### Contributing

Issues and PRs are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) first.

### License

[MIT](LICENSE)

---
