# 贡献指南 / Contributing

感谢关注知源（ZhiYuan）！欢迎 Bug 报告、文档改进与新功能（大功能请先开 Issue 对齐方案）。

Thanks for your interest! Bug reports, docs improvements and features are welcome.
For larger features, please open an issue first to align on the design.

## 开发环境 / Setup

**环境要求：** Python 3.12、Node.js 20+、Docker Desktop、[uv](https://docs.astral.sh/uv/)。

```bash
git clone https://github.com/dhanegle/knowledge-based-system.git
cd knowledge-based-system
cp .env.example .env          # 填写 LLM / Embedding 的 URL、密钥、模型名
bash scripts/dev.sh           # Linux / macOS / Git Bash
# 或 Windows PowerShell：
.\scripts\dev.ps1
```

- 界面：http://localhost:5173
- 接口文档：http://localhost:8000/docs

## 提交前检查 / Before you push

```bash
# 1. 后端测试必须全过（纯逻辑 + API 测试，不需要真实 LLM）
uv run pytest tests/ -q

# 2. 前端可构建
cd frontend && npm run build

# 3. 代码风格（后端）
uv run ruff check app/
```

## 代码约定

- **隔离优先**：任何新增的查询、缓存、历史接口都必须带 `user_id` 作用域——
  对话与缓存按用户隔离是这个产品的底线，回归测试请同步更新 `tests/`。
- **角色最小权限**：新端点必须声明角色要求；admin 不得操作其他 admin 与 owner，
  新权限逻辑要有对应测试（参考 `tests/test_auth.py`）。
- **供应商无关**：LLM / Embedding 一律走 OpenAI 兼容 HTTP，URL 与模型名写配置不写代码。
- **降级可用**：Redis / Langfuse 等可选组件挂掉时主流程必须照常工作。
- **密钥零容忍**：不要在代码、测试、日志、Issue 中出现真实密钥与内部文档内容。

## 提交规范

- commit message 格式 `type: 摘要`，type 取 `feat` / `fix` / `docs` / `test` / `refactor` / `chore`。
- 一个 PR 聚焦一件事；涉及鉴权、隔离、摄入状态机的改动请在描述里附测试输出。

## 安全问题 / Security

漏洞请不要公开 Issue，见 README「安全与隐私」一节：报告走 GitHub Issues 私信或邮件，
不要贴密钥与内部文档内容。
