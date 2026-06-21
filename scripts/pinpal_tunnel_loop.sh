#!/usr/bin/env bash
# Self-healing SSH tunnel for Pin Pal with automatic path fallback.
#
# Launched by pinpal_connect.sh (not meant to be run directly). Reconnects
# forever: tries the direct LAN IP first (fast on the Pi's own network), falls
# back to the stable Tailscale name when the LAN path is unreachable (e.g. you
# moved to a different network), and pops a desktop notification on fallback.
#
# Config comes from the environment, set by pinpal_connect.sh:
#   PINPAL_PRIMARY   direct/LAN host, tried first      (e.g. 10.43.235.204)
#   PINPAL_FALLBACK  Tailscale name, used on fallback  (e.g. pinpal)
#   PINPAL_USER      ssh user                          (e.g. pinpal)
#   PINPAL_KEY       ssh identity file
#   PINPAL_PORT      local tunnel port                 (e.g. 8001)
#   PINPAL_RPORT     remote server port                (e.g. 8000)
#   PINPAL_LOG       log file path
set -u

PRIMARY="${PINPAL_PRIMARY:?}"
FALLBACK="${PINPAL_FALLBACK:?}"
USER_="${PINPAL_USER:?}"
KEY="${PINPAL_KEY:?}"
PORT="${PINPAL_PORT:?}"
RPORT="${PINPAL_RPORT:?}"
LOG="${PINPAL_LOG:?}"

SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=4 -o StrictHostKeyChecking=accept-new
          -o ServerAliveInterval=5 -o ServerAliveCountMax=2
          -o IdentitiesOnly=yes -i "$KEY")

notify() { command -v notify-send >/dev/null 2>&1 && notify-send 'Pin Pal' "$1" >/dev/null 2>&1 || true; }
log()    { echo "$(date): $1" >> "$LOG"; }

last_path=""
while true; do
  # Choose a path: direct LAN IP first, Tailscale name as fallback.
  if ssh "${SSH_OPTS[@]}" "$USER_@$PRIMARY" true 2>/dev/null; then
    host="$PRIMARY"; via="LAN IP ($PRIMARY)"; path="lan"
  elif ssh "${SSH_OPTS[@]}" "$USER_@$FALLBACK" true 2>/dev/null; then
    host="$FALLBACK"; via="Tailscale ($FALLBACK)"; path="tailscale"
  else
    log "neither LAN IP ($PRIMARY) nor Tailscale ($FALLBACK) reachable — retrying in 3s"
    sleep 3; continue
  fi

  # Announce a path change once (especially the LAN -> Tailscale fallback),
  # not on every reconnect.
  if [ "$path" != "$last_path" ]; then
    if [ "$path" = "tailscale" ]; then
      log "LAN IP $PRIMARY unreachable — FALLING BACK to Tailscale ($FALLBACK)"
      notify "LAN IP unreachable — connecting over Tailscale ($FALLBACK)"
    elif [ -n "$last_path" ]; then
      log "LAN IP $PRIMARY reachable again — switching back off Tailscale"
      notify "LAN IP back — switched off Tailscale"
    fi
    last_path="$path"
  fi

  log "tunnel up via $via (localhost:$PORT -> $USER_@$host:$RPORT)"
  ssh -N -L "${PORT}:localhost:${RPORT}" "${SSH_OPTS[@]}" "$USER_@$host"
  log "tunnel via $via dropped, reconnecting in 2s..."
  sleep 2
done
