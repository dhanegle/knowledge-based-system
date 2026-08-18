# 知源（ZhiYuan）

公司个人知识库问答系统 —— 基于 RAG（检索增强生成）架构。

## 快速开始

### 后端

```bash
cp .env.example .env   # 填写 LLM / Embedding 配置
uv sync                # 安装依赖
uv run uvicorn app.main:app --reload --port 8000
```

打开 http://localhost:8000/docs 查看 API 文档。

### 前端

```bash
cd frontend
npm install
npm run dev            # 启动开发服务器 http://localhost:5173
```

前端开发服务器已配置代理，`/api` 请求自动转发到后端 `localhost:8000`。

### 基础设施

```bash
docker compose up -d qdrant postgres redis   # 启动向量库/关系库/缓存
```

### 全栈 Docker 部署

```bash
cp .env.example .env   # 填写 LLM / Embedding 配置
docker compose up -d --build                 # 构建并启动全部服务
```

访问 http://localhost 即可使用完整系统。

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI + SQLAlchemy 2 (async) + Pydantic + JWT |
| 前端 | Vue 3 + Vite + Pinia + Vue Router + Tailwind CSS |
| 向量库 | Qdrant |
| 关系库 | PostgreSQL 16 |
| 缓存 | Redis 7 |
| 部署 | Docker Compose (全栈编排) |

## 当前进度

- [x] 阶段 1：FastAPI 骨架 + LLM 客户端接口 + SSE 流式 `/ask`
- [x] 阶段 2：文档摄入管线（解析 / 分块 / 向量化 / 入库）
- [x] 阶段 3：核心 RAG（检索 / 重排 / 带引用生成）
- [x] 阶段 4：文档管理（CRUD / 增量更新）
- [x] 阶段 5：可观测性（Langfuse / 日志）
- [x] 阶段 6：生产加固（JWT 鉴权 / 错误分类 / Redis 缓存 / 测试）
- [x] 阶段 7：前端 UI + Docker 全栈部署
