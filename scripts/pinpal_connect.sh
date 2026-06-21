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
# Override defaults if needed:
#   PINPAL_HOST=10.43.235.204 PINPAL_USER=pinpal ./scripts/pinpal_connect.sh

set -euo pipefail

PI_HOST="${PINPAL_HOST:-10.43.235.204}"
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

# 2. Is it trusted yet?
if ! ssh -o BatchMode=yes -o ConnectTimeout=6 -o IdentitiesOnly=yes -i "$KEY" \
       "$PI_USER@$PI_HOST" 'echo ok' >/dev/null 2>&1; then
  echo
  echo "Your key isn't authorized on the Pi yet. Send this exact line to whoever"
  echo "manages the Pi and ask them to run scripts/pinpal_authorize.sh with it:"
  echo
  echo "  $PUBKEY"
  echo
  echo "Once they confirm it's added, re-run this script."
  exit 1
fi

# 3. Clear out any tunnel we previously started.
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE" 2>/dev/null)" 2>/dev/null; then
  kill "$(cat "$PID_FILE")" 2>/dev/null || true
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

# 5. Self-healing tunnel: reconnect automatically if the WiFi drops it.
nohup bash -c "
  while true; do
    ssh -N -L ${PORT}:localhost:${PI_REMOTE_PORT} \
      -o ExitOnForwardFailure=yes -o ServerAliveInterval=5 -o ServerAliveCountMax=2 \
      -o IdentitiesOnly=yes -i '${KEY}' '${PI_USER}@${PI_HOST}'
    echo \"\$(date): tunnel dropped, reconnecting in 2s...\" >> '${LOG_FILE}'
    sleep 2
  done
" >> "$LOG_FILE" 2>&1 &
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
