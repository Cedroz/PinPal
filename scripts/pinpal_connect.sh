#!/usr/bin/env bash
# Run this on YOUR OWN laptop to connect Claude Code to the Pin Pal Pi.
#
# What it does:
#   1. Generates a dedicated SSH key for you if you don't have one yet
#      (never shares it — only the .pub line ever leaves your machine).
#   2. Checks whether that key is already trusted by the Pi. If not, prints
#      the .pub line for you to send to whoever runs scripts/pinpal_authorize.sh.
#   3. Opens a self-healing SSH tunnel (laptop:<port> -> Pi:8000), since the
#      venue WiFi has been unreliable for direct HTTP but fine over SSH.
#   4. Registers the tunnel with Claude Code (`claude mcp add`).
#
# Safe to re-run any time (e.g. after sleep/reconnect) — it cleans up its
# previous tunnel first.
#
# Connects over the direct LAN IP first, then falls back to the stable Tailscale
# name if the LAN path is unreachable (e.g. you're on a different network).
#
# Override defaults if needed:
#   PINPAL_HOST=10.43.235.204 PINPAL_TS_HOST=pinpal PINPAL_USER=pinpal ./scripts/pinpal_connect.sh

set -euo pipefail

PI_HOST_PRIMARY="${PINPAL_HOST:-10.43.235.204}"   # direct/LAN path — tried first
PI_HOST_FALLBACK="${PINPAL_TS_HOST:-pinpal}"      # Tailscale MagicDNS name — stable fallback
PI_USER="${PINPAL_USER:-pinpal}"
PI_REMOTE_PORT="${PINPAL_REMOTE_PORT:-8000}"
KEY="$HOME/.ssh/pinpal_ed25519"
STATE_DIR="$HOME/.pinpal"
PID_FILE="$STATE_DIR/tunnel.pid"
LOG_FILE="$STATE_DIR/tunnel.log"
PORT_FILE="$STATE_DIR/tunnel.port"

mkdir -p "$STATE_DIR"

# 1. Dedicated key (passphrase-less by design — it's a deploy-only key, never
#    your personal one, so non-interactive SSH from this script works).
if [ ! -f "$KEY" ]; then
  echo "No Pin Pal key found for you — generating one..."
  ssh-keygen -t ed25519 -f "$KEY" -N "" -C "pinpal-deploy-$(whoami)" -q
fi
PUBKEY="$(cat "$KEY.pub")"

# 2. Find a reachable host that already trusts our key. Try the direct LAN IP
#    first, then fall back to the stable Tailscale name. (The self-healing loop
#    below re-checks this on every reconnect; this is just the initial probe so
#    we can give a clear error before backgrounding anything.)
SSH_PROBE=(-o BatchMode=yes -o ConnectTimeout=4 -o StrictHostKeyChecking=accept-new \
           -o IdentitiesOnly=yes -i "$KEY")
PI_HOST=""
for h in "$PI_HOST_PRIMARY" "$PI_HOST_FALLBACK"; do
  if ssh "${SSH_PROBE[@]}" "$PI_USER@$h" 'echo ok' >/dev/null 2>&1; then
    PI_HOST="$h"
    [ "$h" = "$PI_HOST_FALLBACK" ] && echo "LAN IP $PI_HOST_PRIMARY unreachable — using Tailscale ($PI_HOST_FALLBACK)."
    break
  fi
done

if [ -z "$PI_HOST" ]; then
  echo
  echo "Couldn't reach the Pi with your key over either path:"
  echo "  - LAN IP:    $PI_HOST_PRIMARY"
  echo "  - Tailscale: $PI_HOST_FALLBACK"
  echo
  echo "Either the Pi is offline, or your key isn't authorized yet. If it's the key,"
  echo "send this exact line to whoever manages the Pi (they run scripts/pinpal_authorize.sh):"
  echo
  echo "  $PUBKEY"
  echo
  echo "Then re-run this script."
  exit 1
fi

# 3. Clear out any tunnel we previously started — both the reconnect loop and
#    the ssh child it spawned (otherwise the child keeps holding the port and
#    the next run lands on a different one).
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE" 2>/dev/null)" 2>/dev/null; then
  OLD_PID="$(cat "$PID_FILE")"
  pkill -P "$OLD_PID" 2>/dev/null || true
  kill "$OLD_PID" 2>/dev/null || true
  sleep 1
fi

# 4. Pick a free local port (8001+, so we don't clobber a local dev server on 8000).
port_is_free() {
  ! (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null
}
PORT=8001
while [ "$PORT" -lt 8020 ]; do
  if port_is_free "$PORT"; then
    break
  fi
  PORT=$((PORT + 1))
done
echo "$PORT" > "$PORT_FILE"

# 5. Self-healing tunnel: reconnects automatically if the WiFi drops it, and
#    re-picks the path each time (LAN IP first, Tailscale fallback). The loop
#    logic lives in pinpal_tunnel_loop.sh; we just feed it config and background it.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PINPAL_PRIMARY="$PI_HOST_PRIMARY" PINPAL_FALLBACK="$PI_HOST_FALLBACK" \
PINPAL_USER="$PI_USER" PINPAL_KEY="$KEY" PINPAL_PORT="$PORT" \
PINPAL_RPORT="$PI_REMOTE_PORT" PINPAL_LOG="$LOG_FILE" \
  nohup bash "$SCRIPT_DIR/pinpal_tunnel_loop.sh" >> "$LOG_FILE" 2>&1 &
disown
echo $! > "$PID_FILE"

sleep 2

# 6. Register with Claude Code.
claude mcp remove pin-pal >/dev/null 2>&1 || true
claude mcp add --transport http pin-pal "http://localhost:${PORT}/mcp"

echo
echo "Pin Pal tunnel running on localhost:${PORT} (PID $(cat "$PID_FILE"))."
echo "Logs: $LOG_FILE"
echo "Run 'claude mcp list' to verify — should show pin-pal as Connected."
