#!/bin/bash
# ===========================================
# A股报告门户 — 同步&启动脚本
# ===========================================
PORTAL_DIR="$HOME/a-share-portal"
REPORTS_SRC="$HOME/.openclaw/workspace/reports"
TUNNEL_LOG="$PORTAL_DIR/tunnel.log"
SERVER_LOG="$PORTAL_DIR/server.log"
PORT=8080

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo "======================================"
echo "  🚀 A股报告门户管理工具"
echo "======================================"
echo ""

case "${1:-status}" in
  start)
    echo -e "${YELLOW}▶ 启动 HTTP 服务器...${NC}"
    cd "$PORTAL_DIR"
    python3 -m http.server $PORT > "$SERVER_LOG" 2>&1 &
    echo $! > "$PORTAL_DIR/server.pid"
    echo -e "${GREEN}✅ HTTP 服务器已启动 (PID $(cat $PORTAL_DIR/server.pid))${NC}"

    echo -e "${YELLOW}▶ 启动 SSH Tunnel (localhost.run)...${NC}"
    ssh -o StrictHostKeyChecking=no -R 80:localhost:$PORT nokey@localhost.run > "$TUNNEL_LOG" 2>&1 &
    echo $! > "$PORTAL_DIR/tunnel.pid"
    sleep 3
    TUNNEL_URL=$(grep -oP 'https://[a-z0-9]+\.lhr\.life' "$TUNNEL_LOG" | head -1)
    if [ -n "$TUNNEL_URL" ]; then
      echo "$TUNNEL_URL" > "$PORTAL_DIR/tunnel.url"
      echo -e "${GREEN}✅ Tunnel 已启动 → ${YELLOW}$TUNNEL_URL${NC}"
    else
      echo -e "${RED}⚠️  Tunnel 启动中，请稍后检查 $TUNNEL_LOG${NC}"
    fi
    ;;

  stop)
    if [ -f "$PORTAL_DIR/server.pid" ]; then
      kill $(cat "$PORTAL_DIR/server.pid") 2>/dev/null
      rm -f "$PORTAL_DIR/server.pid"
      echo -e "${GREEN}✅ HTTP 服务器已停止${NC}"
    fi
    if [ -f "$PORTAL_DIR/tunnel.pid" ]; then
      kill $(cat "$PORTAL_DIR/tunnel.pid") 2>/dev/null
      rm -f "$PORTAL_DIR/tunnel.pid"
      echo -e "${GREEN}✅ Tunnel 已停止${NC}"
    fi
    ;;

  restart)
    $0 stop
    sleep 1
    $0 start
    ;;

  sync)
    echo -e "${YELLOW}▶ 同步报告文件...${NC}"
    cp -u "$REPORTS_SRC"/*.html "$PORTAL_DIR/reports/" 2>/dev/null
    cp -u "$REPORTS_SRC"/*.txt "$PORTAL_DIR/reports/" 2>/dev/null
    cp -u "$REPORTS_SRC"/*.pdf "$PORTAL_DIR/reports/" 2>/dev/null
    echo -e "${GREEN}✅ 报告同步完成${NC}"
    echo -e "\n${YELLOW}📋 当前报告列表：${NC}"
    ls -la "$PORTAL_DIR/reports/"
    ;;

  url)
    if [ -f "$PORTAL_DIR/tunnel.url" ]; then
      echo -e "${GREEN}📎 分享链接：${YELLOW}$(cat $PORTAL_DIR/tunnel.url)${NC}"
    else
      echo -e "${RED}⚠️  Tunnel 未启动${NC}"
    fi
    ;;

  status)
    echo -e "${YELLOW}📊 服务状态：${NC}"
    if [ -f "$PORTAL_DIR/server.pid" ] && kill -0 $(cat "$PORTAL_DIR/server.pid") 2>/dev/null; then
      echo -e "  HTTP 服务: ${GREEN}运行中 ✅${NC}"
    else
      echo -e "  HTTP 服务: ${RED}已停止 ❌${NC}"
    fi
    if [ -f "$PORTAL_DIR/tunnel.pid" ] && kill -0 $(cat "$PORTAL_DIR/tunnel.pid") 2>/dev/null; then
      echo -e "  Tunnel:    ${GREEN}运行中 ✅${NC}"
      $0 url
    else
      echo -e "  Tunnel:    ${RED}已停止 ❌${NC}"
    fi
    echo -e "\n${YELLOW}📋 报告数量：${NC}$(ls -1 "$PORTAL_DIR/reports/" 2>/dev/null | wc -l) 份"
    ;;

  *)
    echo "用法: $0 {start|stop|restart|sync|url|status}"
    echo ""
    echo "  start   启动 HTTP 服务器 + SSH Tunnel"
    echo "  stop    停止所有服务"
    echo "  restart 重启所有服务"
    echo "  sync    同步最新报告到门户"
    echo "  url     显示当前分享链接"
    echo "  status  查看服务状态"
    ;;
esac
