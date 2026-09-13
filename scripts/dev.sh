#!/usr/bin/env bash
# 知源 — 一键启动本地开发环境
# 用法: bash scripts/dev.sh
#
# 启动顺序: 基础设施(Docker) → 后端(FastAPI) → 前端(Vite)
# 按 Ctrl+C 会同时关闭后端和前端（基础设施保持运行）。

set -euo pipefail

cd "$(dirname "$0")/.."

# 后端端口优先取 .env 中的 ZHIYUAN_PORT，缺省 8000；可用环境变量覆盖
BACKEND_PORT="${ZHIYUAN_PORT:-}"
if [ -z "${BACKEND_PORT}" ] && [ -f .env ]; then
  BACKEND_PORT="$(grep -E '^ZHIYUAN_PORT=' .env | tail -n1 | cut -d= -f2 | tr -d '[:space:]')"
fi
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT=5173

# ── 1. 启动基础设施 ──
echo "==> 启动基础设施 (Qdrant + Postgres + Redis)..."
docker compose up -d qdrant postgres redis

# ── 2. 检查 .env ──
if [ ! -f .env ]; then
  echo "!! 未找到 .env，从 .env.example 复制一份"
  cp .env.example .env
  echo "   -> 请编辑 .env 填入 LLM / Embedding 的 URL 和 key，然后重新运行本脚本"
  exit 1
fi

# ── 3. 启动后端 ──
echo "==> 启动后端 http://localhost:${BACKEND_PORT}"
uv run uvicorn app.main:app --reload --port "${BACKEND_PORT}" &
BACKEND_PID=$!

# ── 4. 启动前端 ──
echo "==> 启动前端 http://localhost:${FRONTEND_PORT}"
(cd frontend && npm run dev -- --port "${FRONTEND_PORT}") &
FRONTEND_PID=$!

# ── 5. 清理: Ctrl+C 时关闭前后端 ──
cleanup() {
  echo ""
  echo "==> 停止前后端..."
  kill "${BACKEND_PID}" "${FRONTEND_PID}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo ""
echo "──────────────────────────────────────────────"
echo "  前端: http://localhost:${FRONTEND_PORT}"
echo "  后端: http://localhost:${BACKEND_PORT}/docs"
echo "  按 Ctrl+C 停止前后端"
echo "──────────────────────────────────────────────"

wait "${BACKEND_PID}" "${FRONTEND_PID}"
