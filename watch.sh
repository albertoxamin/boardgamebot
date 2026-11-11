#!/bin/bash
# Directory setup — ensures script runs inside the bot directory regardless of working dir
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR" || exit 1

# Load environment variables (including TUNNEL_TOKEN)
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

echo "[$(date)] Starting commit watcher and service keepalive in $REPO_DIR..."

restart_services() {
  echo "[$(date)] Restarting services..."

  # 1. Restart Telegram Bot
  pkill -f "python3 bot.py" || true
  sleep 1
  nohup python3 bot.py > bot.log 2>&1 &
  echo "[$(date)] Bot restarted (PID: $!)."

  # 2. Restart Cloudflare Tunnel using local binary
  if [ -n "$TUNNEL_TOKEN" ]; then
    pkill -f "cloudflared-bin tunnel" || true
    sleep 1
    nohup ./cloudflared-bin tunnel run --token "$TUNNEL_TOKEN" > tunnel.log 2>&1 &
    echo "[$(date)] Cloudflare Tunnel restarted (PID: $!)."
  else
    echo "[$(date)] Warning: TUNNEL_TOKEN not found in .env — skipping tunnel restart."
  fi
}

# Ensure both processes are running on initial execution
if ! pgrep -f "python3 bot.py" > /dev/null || ! pgrep -f "cloudflared-bin tunnel" > /dev/null; then
  echo "[$(date)] One or more services down. Starting initial instances..."
  restart_services
fi

# Main monitoring loop (checks every 60 seconds)
while true; do
  git fetch origin > /dev/null 2>&1

  LOCAL=$(git rev-parse HEAD)
  REMOTE=$(git rev-parse @{u})

  if [ "$LOCAL" != "$REMOTE" ]; then
    echo "[$(date)] New commit detected on remote! Pulling changes..."
    git pull origin $(git rev-parse --abbrev-ref HEAD)
    restart_services
  else
    # Auto-heal: restart individual processes if they crash without a new commit
    if ! pgrep -f "python3 bot.py" > /dev/null; then
      echo "[$(date)] Bot process died! Recovering..."
      nohup python3 bot.py > bot.log 2>&1 &
    fi
    if [ -n "$TUNNEL_TOKEN" ] && ! pgrep -f "cloudflared-bin tunnel" > /dev/null; then
      echo "[$(date)] Cloudflare Tunnel process died! Recovering..."
      nohup ./cloudflared-bin tunnel run --token "$TUNNEL_TOKEN" > tunnel.log 2>&1 &
    fi
  fi

  sleep 60
done
