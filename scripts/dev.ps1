# 知源 — 一键启动本地开发环境 (Windows PowerShell)
# 用法: 右键"使用 PowerShell 运行"，或在 PowerShell 中执行 .\scripts\dev.ps1

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

# ── 1. 启动基础设施 ──
Write-Host "==> 启动基础设施 (Qdrant + Postgres + Redis)..." -ForegroundColor Cyan
docker compose up -d qdrant postgres redis

# ── 2. 检查 .env ──
if (-not (Test-Path .env)) {
  Copy-Item .env.example .env
  Write-Host "   -> 已从 .env.example 创建 .env，请填写 LLM / Embedding 配置后重新运行" -ForegroundColor Yellow
  exit 1
}

# ── 3. 启动后端 (新窗口) ──
# 后端端口优先取 .env 中的 ZHIYUAN_PORT，缺省 8000
$BackendPort = "8000"
$EnvLine = Select-String -Path .env -Pattern '^ZHIYUAN_PORT=' | Select-Object -Last 1
if ($EnvLine) {
  $Parsed = ($EnvLine.Line -split '=', 2)[1].Trim()
  if ($Parsed) { $BackendPort = $Parsed }
}
Write-Host "==> 启动后端 http://localhost:$BackendPort" -ForegroundColor Cyan
Start-Process powershell -ArgumentList '-NoExit','-Command',"uv run uvicorn app.main:app --reload --port $BackendPort"

# ── 4. 启动前端 (新窗口) ──
Write-Host "==> 启动前端 http://localhost:5173" -ForegroundColor Cyan
Start-Process powershell -ArgumentList '-NoExit','-Command','cd frontend; npm run dev'

Write-Host ""
Write-Host "  前端: http://localhost:5173" -ForegroundColor Green
Write-Host "  后端: http://localhost:$BackendPort/docs" -ForegroundColor Green
Write-Host "  后端和前端分别运行在两个新窗口中，关闭窗口即停止对应服务" -ForegroundColor Gray
