# 🚀 A股市场分析工具 v2.5 - 一键安装脚本 (Windows PowerShell)
# 用法: 以管理员身份运行 PowerShell，执行:
#   iex (iwr -useb https://raw.githubusercontent.com/oy07150619-ux/a-share-master/main/install.ps1)

$ErrorActionPreference = "Stop"
$REPO = "https://github.com/oy07150619-ux/a-share-master.git"
$SKILL_DIR = "$env:USERPROFILE\.openclaw\workspace\skills\a-share-master"
$TOOLS_DIR = "$env:USERPROFILE\.openclaw\workspace\tools"

Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "  📊 A股市场分析工具 v2.5 头部券商级" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""

# 1. 检查OpenClaw
if (-not (Get-Command openclaw -ErrorAction SilentlyContinue)) {
    Write-Host "⚠️  未检测到OpenClaw，请先安装:" -ForegroundColor Yellow
    Write-Host "   iwr -useb https://openclaw.ai/install.ps1 | iex" -ForegroundColor White
    exit 1
}

# 2. 创建工作目录
Write-Host "📁 创建工作目录..." -ForegroundColor Green
New-Item -ItemType Directory -Path "$env:USERPROFILE\.openclaw\workspace" -Force | Out-Null
if (Test-Path $SKILL_DIR) {
    Write-Host "   ⚠️  检测到已存在，先备份旧版本..." -ForegroundColor Yellow
    mv $SKILL_DIR "$SKILL_DIR.bak.$(Get-Date -Format 'yyyyMMddHHmmss')" -Force
}

# 3. 克隆技能
Write-Host "📦 下载技能包..." -ForegroundColor Green
git clone $REPO $SKILL_DIR 2>&1 | Out-Null

# 4. 复制tools依赖
Write-Host "🔧 安装工具依赖..." -ForegroundColor Green
New-Item -ItemType Directory -Path $TOOLS_DIR -Force | Out-Null
Copy-Item "$SKILL_DIR\tools\*.py" $TOOLS_DIR -Force

# 5. 安装Python依赖
Write-Host "🐍 安装Python包..." -ForegroundColor Green
pip install akshare requests --quiet 2>&1 | Out-Null

# 6. 配置邮箱（需要用户手动修改）
Write-Host ""
Write-Host "✅ v2.5 头部券商级 安装完成!" -ForegroundColor Green
Write-Host ""
Write-Host "📌 下一步：配置邮箱发送" -ForegroundColor Yellow
Write-Host "   编辑 $SKILL_DIR\..\..\..\tools\email_report.py" -ForegroundColor White
Write-Host "   修改 TO_EMAIL 为你自己的邮箱地址" -ForegroundColor White
Write-Host ""
Write-Host "📌 然后配置定时任务（每天自动发送报告）：" -ForegroundColor Yellow
Write-Host "   打开OpenClaw TUI 或 使用 openclaw cron 命令" -ForegroundColor White
Write-Host "   参考 $SKILL_DIR\SKILL.md 中的配置说明" -ForegroundColor White
Write-Host ""
Write-Host "📌 数据采集验证：" -ForegroundColor Yellow
Write-Host "   python $SKILL_DIR\scripts\collector.py all" -ForegroundColor White
