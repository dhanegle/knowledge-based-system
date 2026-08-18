# 知源（ZhiYuan）

公司个人知识库问答系统 —— 基于 RAG（检索增强生成）架构。

## 快速开始

```bash
cp .env.example .env   # 填写配置（LLM key 暂可留空，用占位实现）
uv sync                # 安装依赖
uv run uvicorn app.main:app --reload --port 8000
```

打开 http://localhost:8000/docs 查看 API 文档。

## 基础设施

```bash
docker compose up -d qdrant postgres   # 启动向量库和关系库
```

## 当前进度

- [x] 阶段 1：FastAPI 骨架 + LLM 客户端接口 + SSE 流式 `/ask`
- [x] 阶段 2：文档摄入管线（解析 / 分块 / 向量化 / 入库）
- [ ] 阶段 3：核心 RAG（检索 / 重排 / 带引用生成）
- [ ] 阶段 4：文档管理（CRUD / 增量更新）
- [ ] 阶段 5：可观测性（Langfuse / 日志）
- [ ] 阶段 6：生产加固（鉴权 / 测试 / 缓存）
- [ ] 阶段 7：前端 UI + Docker 部署
