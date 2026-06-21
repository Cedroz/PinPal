# Pin Pal — laptop side (`app/`)

The companion that runs on the **developer's laptop**, next to the Pi's `pin-pal` probe
server. This folder is **Person B's piece**: the netlist confirmation UI and the MCP gate
that opens it.

When the vision agent parses a breadboard photo into a netlist, Claude calls the
`confirm_netlist` tool. That pops a **desktop window** (react-flow circuit editor wrapped
in a native pywebview window), the user fixes any mistakes, and the **approved** netlist is
returned to the chat. Nothing the agent merely *guessed* reaches the model — only what a
human confirmed. This is the human-gate step from [PIN_PAL.md](PIN_PAL.md#L80-L115).

```
vision agent ──netlist JSON──► confirm_netlist()  ──►  pywebview window (react-flow)
 (Person A)                      (pin-pal-ui MCP)         user edits + approves
                                       ▲                         │
                                       └──── corrected netlist ───┘
```

## Layout

| Path | What it is |
| --- | --- |
| `schema.py` | **The contract.** Netlist shape (components + nets) + validation. Mirrors `web/src/netlist.ts`. Shared with Person A. |
| `sample_netlist.json` | A worked LED-circuit netlist used as a fixture / dev fallback. |
| `web/` | React + `@xyflow/react` editor (Vite). Built to `web/dist/`. |
| `netlist_window.py` | Standalone pywebview window. Reads netlist on stdin, returns the corrected one. Run as a subprocess. |
| `ui_server.py` | `pin-pal-ui` stdio MCP server exposing `confirm_netlist`. |

## How the pieces fit

- **`confirm_netlist` blocks** until the user approves. It launches `netlist_window.py` as a
  **subprocess** — pywebview's event loop can only start once per process and must not share
  a thread with the MCP server's asyncio loop, so one fresh subprocess per confirmation is
  the clean design.
- **Edges are the source of truth.** In the editor, wires are react-flow edges. On approve,
  nets are rebuilt from the edge graph via union-find (`web/src/netlist.ts`), so the user can
  add / delete / reconnect wires freely and connectivity is recovered correctly.

## Setup

**1. Build the web UI** (produces `web/dist/`, which the window loads over `file://`):

```bash
cd app/web
npm install
npm run build      # or: npm run dev  — opens the editor in a browser with the sample netlist
```

**2. Python env + a webview backend.** pywebview needs a native webview to render. On Linux:

```bash
cd app
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
# Linux backend — GTK4 + WebKit (Debian/Ubuntu):
sudo apt install -y python3-gi gir1.2-gtk-4.0 gir1.2-webkit-6.0
#   …or use Qt instead:  pip install "pywebview[qt]"
```

(macOS/Windows need no extra backend — pywebview uses the OS webview.)

## Wire it into Claude Code

`.mcp.json` at the repo root already registers the stdio server (relative paths resolve from
the project root):

```json
{ "mcpServers": { "pin-pal-ui": { "type": "stdio",
  "command": "app/.venv/bin/python", "args": ["app/ui_server.py"] } } }
```

The Pi's probe server is added separately (it's HTTP, on the LAN):

```bash
claude mcp add --transport http pin-pal http://<PI_LAN_IP>:8000/mcp
```

**Long-edit timeout.** `confirm_netlist` blocks while the user edits — this can take minutes.
The relevant timeout is `API_TIMEOUT_MS` (default **10 min**), which governs the whole tool
call. It is **not** settable in `.mcp.json`'s `env` block (that only configures the
subprocess). If you expect edits longer than 10 minutes, set it on the Claude Code process —
e.g. in `~/.claude/settings.json`:

```json
{ "env": { "API_TIMEOUT_MS": "1200000" } }
```

## Dev loop without the Pi

`npm run dev` runs the editor in a plain browser. With no pywebview host present, `bridge.ts`
falls back to the baked-in sample netlist and logs Approve/Cancel to the console — so the
whole editor is iterable standalone, no Pi or MCP server needed.

## Verified

- `web` builds clean (`npm run build`).
- `schema.py` round-trips and rejects malformed netlists.
- `confirm_netlist` registers and rejects bad input before opening a window.
- netlist → graph → netlist round-trip preserves connectivity and net names; user wire edits
  re-derive nets correctly (union-find).

**Not yet verified end-to-end:** the live window render + click-to-approve, which needs a
webview backend + display (see Setup). Test on the laptop with `npm run build` done.

## Contract with Person A (vision agent)

The seam is `schema.py` (the netlist JSON) and the `confirm_netlist(netlist) -> {status, netlist}`
tool. Person A emits a netlist matching the schema and calls `confirm_netlist`; the approved
result is what flows into the chat. Keep `schema.py` and `web/src/netlist.ts` in lockstep.
