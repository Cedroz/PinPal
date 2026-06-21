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
import os
import pathlib
import sys

# QtWebEngine defaults to hardware OpenGL. On headless / GPU-less X servers (VMs, CI,
# SSH-forwarded displays) that path can't get a GL context, falls back to Vulkan, and
# crashes the process with SIGSEGV. Force Chromium + Qt onto software rendering before
# any Qt import. setdefault so a host with a working GPU can still override these.
if sys.platform.startswith("linux"):
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")
    os.environ.setdefault("QT_OPENGL", "software")
    os.environ.setdefault("QT_QUICK_BACKEND", "software")  # render QtWebEngine's QQuickWidget
                                                           # in software; without it the web
                                                           # view gets no RHI and stays blank
    os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")

import webview

INDEX = pathlib.Path(__file__).parent / "web" / "dist" / "index.html"

# On Linux pywebview tries GTK first (needs system PyGObject) before falling back to Qt.
# We ship the Qt backend via pip, so select it directly and skip the noisy GTK attempt.
# An explicit PYWEBVIEW_GUI override still wins. macOS/Windows use the native webview.
_GUI = "qt" if sys.platform.startswith("linux") and not os.environ.get("PYWEBVIEW_GUI") else None


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
        on_top=True,  # float above the editor that launched us; this is a blocking modal,
                      # so stay on top until the user approves or cancels rather than getting
                      # lost behind a maximized window.
    )
    webview.start(gui=_GUI)  # blocks until the window is destroyed

    payload = json.dumps(result)
    if out_path:
        pathlib.Path(out_path).write_text(payload)
    else:
        print(payload)


if __name__ == "__main__":
    main()
