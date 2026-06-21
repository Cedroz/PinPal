#!/usr/bin/env bash
# onboard.sh — one-shot Pin Pal onboarding. Idempotent: every step runs only if needed,
# so it's safe to re-run any time (e.g. after a fresh clone, or to connect the Pi later).
#
#   1. Build the netlist editor web UI          (skips if web/dist/ is up to date)
#   2. Python venv + deps for pin-pal-ui         (skips if .venv already has the deps)
#   3. pin-pal-ui MCP                            (registered via .mcp.json; clears stray dup)
#   4. Connect the Pi's pin-pal probe server     (always over SSH tunnel; skips if added)
#
# Run from the repo root:  ./onboard.sh
# Needs: node/npm, python3, and the `claude` CLI on PATH.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP="$ROOT/app"

ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; }
run() { printf '  \033[33m→\033[0m %s\n' "$1"; }

# --- 1. web UI -------------------------------------------------------------
echo "[1/4] Netlist editor (web/dist/)"
if [ -f "$APP/web/dist/index.html" ] && \
   [ -z "$(find "$APP/web/src" -newer "$APP/web/dist/index.html" 2>/dev/null)" ]; then
  ok "already built and up to date"
else
  run "building…"
  ( cd "$APP/web" && npm install && npm run build )
fi

# --- 2. python env ---------------------------------------------------------
echo "[2/4] Python venv + requirements"
if [ -x "$APP/.venv/bin/python" ] && "$APP/.venv/bin/python" -c "import webview, mcp" 2>/dev/null; then
  ok ".venv already present with deps"
else
  run "creating venv + installing…"
  python3 -m venv "$APP/.venv"
  "$APP/.venv/bin/pip" install --upgrade pip
  "$APP/.venv/bin/pip" install -r "$APP/requirements.txt"
fi

# --- 3. pin-pal-ui (laptop MCP) --------------------------------------------
# .mcp.json registers it at project scope; just clear any stray local duplicate.
echo "[3/4] pin-pal-ui MCP"
claude mcp remove pin-pal-ui -s local >/dev/null 2>&1 || true
ok "registered via .mcp.json — approve it when you launch claude in this repo"

# --- 4. pin-pal (Pi probe server) ------------------------------------------
# Always over the SSH tunnel — never a direct LAN/HTTP add.
echo "[4/4] pin-pal MCP (the Pi probe server, over SSH tunnel)"
if claude mcp list 2>/dev/null | grep -q '^pin-pal:'; then
  ok "already registered — skipping"
else
  run "opening SSH tunnel via scripts/pinpal_connect.sh…"
  # First run exits non-zero on purpose: it generates your key and prints it for the Pi's
  # owner to authorize. Don't let that abort onboarding (we run under `set -e`).
  if "$ROOT/scripts/pinpal_connect.sh"; then
    ok "pin-pal connected over the SSH tunnel"
  else
    run "send the public key printed above to the Pi's owner (scripts/pinpal_authorize.sh),"
    run "then re-run ./onboard.sh to finish registering pin-pal"
  fi
fi

echo
echo "Done. Verify with:  claude mcp list"
