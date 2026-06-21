# Pin Pal — Setup

Pin Pal is two MCP servers:

- **`pin-pal-ui`** — runs on your **laptop** (this `app/` folder). The netlist confirm window.
- **`pin-pal`** — runs on the **Pi**. The hardware probes (`scan_i2c`, `read_gpio`, `capture_circuit`, …).

## Application side (your laptop)

One idempotent script does the whole laptop setup — builds the UI, creates the venv,
installs deps, fixes up the `pin-pal-ui` MCP, and (step 4) prompts for the Pi's IP to
connect `pin-pal`. Safe to re-run; each step is skipped when already done.

```bash
./onboard.sh
```

Needs `node`/`npm`, `python3`, and the `claude` CLI on PATH. On Linux the Qt webview
backend installs via pip (no sudo, no `--system-site-packages`). macOS/Windows use the
OS-native webview — nothing extra.

Verify:

```bash
claude mcp list      # pin-pal-ui → Connected
```

Notes:
- The confirm window needs a **graphical session** — run `claude` from a terminal *inside*
  your desktop (so `DISPLAY`, `XAUTHORITY`, `DBUS_SESSION_BUS_ADDRESS` are inherited). A bare
  SSH shell won't render it.
- Edits can take minutes, and the tool call blocks the whole time. If you expect long edits,
  raise the timeout in `~/.claude/settings.json`: `{ "env": { "API_TIMEOUT_MS": "1200000" } }`.

## Pi side (the probe server)

On the **Pi**, start the probe server:

```bash
cd pi
pip install -r ../requirements.txt
sudo apt-get install -y python3-picamera2 arduino-cli i2c-tools   # system packages
python server.py                                                  # serves on 0.0.0.0:8000
```

Then connect from your laptop. Connection is **always over an SSH tunnel — never a direct
LAN/HTTP add.** `./scripts/pinpal_connect.sh` generates a key, forwards the Pi's `:8000` to a
local port, and registers `pin-pal` (pointed at `localhost`) for you:

```bash
./scripts/pinpal_connect.sh
```

(`./onboard.sh` runs this same tunnel step as part of full first-time setup.)

Verify:

```bash
claude mcp list      # pin-pal → Connected (6 tools)
```
