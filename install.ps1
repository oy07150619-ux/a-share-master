# 🚀 安装 A股市场分析工具 v3.0
# Windows PowerShell (管理员运行)
# 用法:
#   iwr -useb https://openclaw.ai/install.ps1 | iex
#   git clone https://github.com/oy07150619-ux/a-share-master.git ~/.openclaw/workspace/skills/a-share-master
#   pip install akshare requests

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  安装 A股市场分析工具 v3.0" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 第1步: 安装 OpenClaw (如已安装可跳过)
if (-not (Get-Command openclaw -ErrorAction SilentlyContinue)) {
    Write-Host "▶ 第1步: 安装 OpenClaw" -ForegroundColor Yellow
    iex (iwr -useb https://openclaw.ai/install.ps1).Content
    openclaw onboard --install-daemon
} else {
    Write-Host "✅ OpenClaw 已安装" -ForegroundColor Green
}

# 第2步: 安装市场分析工具 skill
Write-Host "`n▶ 第2步: 安装市场分析工具 skill" -ForegroundColor Yellow
$SKILL_DIR = "$env:USERPROFILE\.openclaw\workspace\skills\a-share-master"
if (Test-Path $SKILL_DIR) {
    Remove-Item $SKILL_DIR -Recurse -Force
}
git clone https://github.com/oy07150619-ux/a-share-master.git $SKILL_DIR

# 第3步: 安装 Python 依赖
Write-Host "`n▶ 第3步: 安装 Python 依赖" -ForegroundColor Yellow
pip install akshare requests --quiet

Write-Host "`n✅ 安装完成!" -ForegroundColor Green
Write-Host "📧 编辑 $SKILL_DIR\..\..\..\tools\email_report.py 修改 TO_EMAIL" -ForegroundColor Yellow
Write-Host "⏰ 参考 SKILL.md 配置定时任务" -ForegroundColor Yellow