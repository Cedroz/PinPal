"""Standalone pywebview window that shows the netlist editor and blocks until the user
approves or cancels.

Run as a subprocess by ui_server.py (pywebview's webview.start() can only run once per
process, and the GUI loop must not share a thread with the MCP asyncio loop — a fresh
subprocess per confirmation sidesteps both).

Protocol:
  stdin  : netlist JSON (the parsed netlist to review)
  argv[1]: path to write the result JSON to
  result : {"status": "approved", "netlist": {...}}  or  {"status": "cancelled"}
"""

import json
import pathlib
import sys

import webview

INDEX = pathlib.Path(__file__).parent / "web" / "dist" / "index.html"


def main() -> None:
    out_path = sys.argv[1] if len(sys.argv) > 1 else None
    raw = sys.stdin.read()
    netlist = json.loads(raw) if raw.strip() else {"components": [], "nets": []}

    if not INDEX.exists():
        sys.exit("Netlist UI is not built. Run: cd app/web && npm install && npm run build")

    result = {"status": "cancelled"}

    class Api:
        def get_netlist(self):
            return netlist

        def submit(self, corrected):
            nonlocal result
            result = {"status": "approved", "netlist": corrected}
            window.destroy()

        def cancel(self):
            window.destroy()

    window = webview.create_window(
        "Pin Pal — Confirm Netlist",
        url=INDEX.as_uri(),
        js_api=Api(),
        width=1100,
        height=760,
        min_size=(720, 520),
    )
    webview.start()  # blocks until the window is destroyed

    payload = json.dumps(result)
    if out_path:
        pathlib.Path(out_path).write_text(payload)
    else:
        print(payload)


if __name__ == "__main__":
    main()
