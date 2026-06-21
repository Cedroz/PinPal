#!/usr/bin/env bash
# run_server.sh — run the Pin Pal MCP server on the Pi, persistently.
#
# Two modes:
#   ./run_server.sh            run the server in the foreground after ensuring
#                              Tailscale is connected and the venv is ready.
#                              This is the entrypoint systemd execs.
#   ./run_server.sh install    install + enable a systemd service so the server
#                              starts on boot and restarts if it crashes, then
#                              start it now.
#
# Persistence is a systemd *user* service. Linger is enabled for this user, so
# the service autostarts at boot without anyone logging in — no sudo needed.
# Idempotent: safe to re-run.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # ~/PinPal
VENV="$ROOT/.venv-pi"                                     # canonical venv (see provision.sh)
SERVER_DIR="$ROOT/pi"
PORT=8000
SERVICE="pinpal-server"

log() { printf '[pinpal] %s\n' "$1"; }

# tailscaled is its own system service and already autostarts at boot; here we
# just wait for this node to be connected before serving, and try to bring it
# up if it isn't. Never fatal — the server still binds 0.0.0.0:$PORT and stays
# reachable over the LAN even if Tailscale is down.
ensure_tailscale() {
  if ! command -v tailscale >/dev/null 2>&1; then
    log "tailscale not installed — skipping (LAN only)"
    return 0
  fi
  for _ in $(seq 1 10); do
    if tailscale status >/dev/null 2>&1; then
      log "tailscale up ($(tailscale ip -4 2>/dev/null | head -1))"
      return 0
    fi
    sudo -n tailscale up >/dev/null 2>&1 || tailscale up >/dev/null 2>&1 || true
    sleep 2
  done
  log "WARNING: tailscale not connected after 20s — continuing on LAN only"
}

ensure_venv() {
  if [ ! -x "$VENV/bin/python" ]; then
    log "venv missing — creating (--system-site-packages so picamera2 is visible)…"
    python3 -m venv --system-site-packages "$VENV"
    "$VENV/bin/pip" install --upgrade -q pip
    "$VENV/bin/pip" install -q -r "$ROOT/requirements.txt"
  elif ! "$VENV/bin/python" -c "import mcp" >/dev/null 2>&1; then
    log "deps missing — installing requirements…"
    "$VENV/bin/pip" install -q -r "$ROOT/requirements.txt"
  fi
  log "venv ready"
}

run_server() {
  ensure_tailscale
  ensure_venv
  log "starting MCP server on 0.0.0.0:$PORT…"
  cd "$SERVER_DIR"                       # so `from display import Display` resolves
  exec "$VENV/bin/python" server.py
}

install_service() {
  local unit_dir="$HOME/.config/systemd/user"
  mkdir -p "$unit_dir"
  cat > "$unit_dir/$SERVICE.service" <<EOF
[Unit]
Description=Pin Pal MCP server
After=network-online.target

[Service]
Type=simple
ExecStart=$SERVER_DIR/run_server.sh
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
EOF
  # Linger lets the user service start at boot with no login session.
  loginctl enable-linger "$(id -un)" >/dev/null 2>&1 || true
  systemctl --user daemon-reload
  systemctl --user enable --now "$SERVICE.service"
  log "installed + started $SERVICE — check: systemctl --user status $SERVICE"
}

case "${1:-run}" in
  run)     run_server ;;
  install) install_service ;;
  *) echo "usage: $0 [run|install]" >&2; exit 1 ;;
esac
