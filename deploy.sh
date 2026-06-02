#!/bin/bash
# ===========================================
# 报告推送 GitHub Pages — 自动部署
# 在每份报告生成后调用，同步到永久链接
# ===========================================
set -e

PORTAL_DIR="$HOME/a-share-portal"
REPORTS_SRC="$HOME/.openclaw/workspace/reports"
REPO_URL="https://github.com/oy07150619-ux/a-share-master.git"

# 1. 同步报告文件
echo "▶ 同步报告..."
cp -u "$REPORTS_SRC"/*.html "$PORTAL_DIR/reports/" 2>/dev/null || true
cp -u "$REPORTS_SRC"/*.txt "$PORTAL_DIR/reports/" 2>/dev/null || true
cp -u "$REPORTS_SRC"/*.pdf "$PORTAL_DIR/reports/" 2>/dev/null || true

# 2. 写入更新时间和报告数量脚本变量
COUNT=$(ls -1 "$PORTAL_DIR/reports/" 2>/dev/null | wc -l)
echo "   共 $COUNT 份报告"

# 3. Git 提交 & 推送
cd "$PORTAL_DIR"
git add -A
if git diff --cached --quiet; then
  echo "   无变化，跳过"
else
  git commit -m "📊 同步报告 $(date +%Y-%m-%d_%H:%M)"
  git push origin gh-pages --force
  echo "✅ 已推送到 GitHub Pages"
fi

# 4. 返回新链接
echo ""
echo "📎 永久链接: https://oy07150619-ux.github.io/a-share-master/"
