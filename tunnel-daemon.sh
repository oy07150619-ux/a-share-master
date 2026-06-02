#!/bin/bash
# 持久化隧道守护脚本 — auto reconnect
PORT=8080
PORTAL_DIR="$HOME/a-share-portal"

# 先确保 HTTP 服务器运行
if ! pgrep -f "python3 -m http.server $PORT" > /dev/null; then
  cd "$PORTAL_DIR" && python3 -m http.server $PORT > "$PORTAL_DIR/server.log" 2>&1 &
  echo "[$(date)] HTTP server restarted" >> "$PORTAL_DIR/daemon.log"
fi

# SSH 隧道 — 自动重连
while true; do
  ssh -o StrictHostKeyChecking=no \
      -o ServerAliveInterval=30 \
      -o ServerAliveCountMax=3 \
      -R 80:localhost:$PORT \
      nokey@localhost.run 2>&1 | \
  while IFS= read -r line; do
    echo "$line" >> "$PORTAL_DIR/tunnel.log"
    # 抓取最新的 URL
    url=$(echo "$line" | grep -oP 'https://[a-z0-9]+\.lhr\.life')
    if [ -n "$url" ]; then
      echo "$url" > "$PORTAL_DIR/tunnel.url"
      echo "[$(date)] Tunnel URL: $url" >> "$PORTAL_DIR/daemon.log"
    fi
  done
  echo "[$(date)] Tunnel disconnected, reconnecting in 3s..." >> "$PORTAL_DIR/daemon.log"
  sleep 3
done
