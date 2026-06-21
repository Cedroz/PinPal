#!/usr/bin/env bash
# provision.sh — one-time Pin Pal Pi setup. Run this ON THE PI, as the Pi's own
# user, to prepare the dependencies: after this, the Python venv is built and
# auto-activated on every login, so you can run server.py by hand without
# reactivating anything.
#
#   1. System packages (camera, I2C, mDNS)
#   2. mDNS hostname  → advertises pinpal.local
#   3. Enable I2C
#   4. Python venv (--system-site-packages, so picamera2 is visible) + deps
#   5. Auto-activate the venv on login (no systemd / persistent server yet)
#
# Run from the repo:  ./pi/provision.sh   (or: cd pi && ./provision.sh)
# Idempotent — safe to re-run after a git pull to pick up changes.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT/.venv-pi"

ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; }
run() { printf '  \033[33m→\033[0m %s\n' "$1"; }

# --- 1. system packages ----------------------------------------------------
echo "[1/5] System packages"
run "apt-get install (camera, I2C, mDNS)…"
sudo apt-get update -qq
sudo apt-get install -y \
  python3-picamera2 i2c-tools \
  python3-venv \
  avahi-daemon avahi-utils libnss-mdns
ok "system packages present"

# --- 2. mDNS hostname (pinpal.local) ---------------------------------------
echo "[2/5] mDNS hostname"
sudo systemctl enable --now avahi-daemon
if [ "$(hostnamectl --static)" != "pinpal" ]; then
  run "setting hostname to 'pinpal' (advertises pinpal.local)…"
  sudo hostnamectl set-hostname pinpal
  ok "hostname set — pinpal.local"
else
  ok "hostname already 'pinpal' — pinpal.local"
fi

# --- 3. enable I2C + SPI ---------------------------------------------------
echo "[3/5] I2C + SPI interfaces"
if [ "$(sudo raspi-config nonint get_i2c)" != "0" ]; then
  run "enabling I2C via raspi-config…"
  sudo raspi-config nonint do_i2c 0
  ok "I2C enabled"
else
  ok "I2C already enabled"
fi
# SPI drives the ST7789 status display. /dev/spidev0.0 only appears after a reboot.
if [ "$(sudo raspi-config nonint get_spi)" != "0" ]; then
  run "enabling SPI via raspi-config…"
  sudo raspi-config nonint do_spi 0
  ok "SPI enabled — REBOOT required before /dev/spidev0.0 exists"
else
  ok "SPI already enabled"
fi

# --- 4. python venv + deps -------------------------------------------------
# --system-site-packages so the apt-installed picamera2 is importable from the
# venv — otherwise capture_image/capture_circuit silently fall back to OpenCV.
echo "[4/5] Python venv + requirements"
if [ ! -x "$VENV_DIR/bin/python" ]; then
  run "creating venv (--system-site-packages)…"
  python3 -m venv --system-site-packages "$VENV_DIR"
fi
run "installing requirements…"
"$VENV_DIR/bin/pip" install --upgrade -q pip
"$VENV_DIR/bin/pip" install -q -r "$ROOT/requirements.txt"
"$VENV_DIR/bin/python" -c "import mcp" || { echo "mcp failed to import — aborting" >&2; exit 1; }
if "$VENV_DIR/bin/python" -c "import picamera2" 2>/dev/null; then
  ok "venv ready (picamera2 visible)"
else
  ok "venv ready"
  run "warning: picamera2 not importable — camera will fall back to OpenCV"
fi

# --- 5. auto-activate the venv on login ------------------------------------
# Source the venv from the login shell so an interactive session always has it
# active — no `source .venv-pi/bin/activate` needed before running server.py.
echo "[5/5] Auto-activate venv on login"
ACTIVATE_LINE="source \"$VENV_DIR/bin/activate\""
MARKER="# pin-pal venv auto-activate"
if ! grep -qF "$MARKER" "$HOME/.bashrc" 2>/dev/null; then
  run "adding venv auto-activate to ~/.bashrc…"
  printf '\n%s\n%s\n' "$MARKER" "$ACTIVATE_LINE" >> "$HOME/.bashrc"
  ok "venv will auto-activate on next login"
else
  ok "venv auto-activate already in ~/.bashrc"
fi

echo
echo "Done. Dependencies installed; venv auto-activates on login."
echo "Start the server by hand:  python \"$ROOT/pi/server.py\""
