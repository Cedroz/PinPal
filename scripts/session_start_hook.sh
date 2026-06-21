#!/usr/bin/env bash
# Claude Code SessionStart hook: ensure the Pin Pal tunnel is running.
#
# Registered into ~/.claude/settings.json by onboard.sh. On each session start
# it checks the local tunnel port: if it's already answering, it does nothing;
# otherwise it (re)launches the canonical connector (pinpal_connect.sh, next to
# this file), which opens the self-healing LAN-IP-first -> Tailscale-fallback
# tunnel. It never opens its own tunnel, so it can't race the reconnect loop.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONNECT="$SCRIPT_DIR/pinpal_connect.sh"
STATE_DIR="$HOME/.pinpal"
PORT="$(cat "$STATE_DIR/tunnel.port" 2>/dev/null || echo 8001)"

port_open() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null && { exec 3>&- 3<&-; return 0; }; return 1; }

if port_open "$PORT"; then
  echo "Pin Pal: tunnel already up on localhost:$PORT."
  exit 0
fi

if [ ! -f "$CONNECT" ]; then
  echo "Pin Pal: connector not found at $CONNECT — skipping."
  exit 0
fi

echo "Pin Pal: tunnel down — starting connector…"
command -v notify-send >/dev/null 2>&1 && notify-send "Pin Pal" "Tunnel down — reconnecting…" >/dev/null 2>&1 || true
mkdir -p "$STATE_DIR"
nohup bash "$CONNECT" >> "$STATE_DIR/connect.log" 2>&1 &
disown
exit 0
