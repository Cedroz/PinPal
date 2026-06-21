"""pin-pal-ui — a local stdio MCP server that runs on the developer's laptop alongside
the Pi's HTTP `pin-pal` probe server.

Its one tool, `confirm_netlist`, is the human gate from the netlist pipeline
(PIN_PAL.md): it pops up the editor, blocks until the user reviews/corrects the parsed
netlist, and returns the approved version. Because the corrected netlist only ever comes
back through this gate, no hallucinated wiring reaches the chat unconfirmed.
"""

import json
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import schema  # noqa: E402  (flat app/ dir — load sibling module)

from mcp.server.fastmcp import FastMCP  # noqa: E402

mcp = FastMCP("pin-pal-ui")

WINDOW = pathlib.Path(__file__).parent / "netlist_window.py"


@mcp.tool()
def confirm_netlist(netlist: dict) -> dict:
    """Open the netlist editor for the user to review and correct the parsed circuit,
    then block until they approve it. Call this with the netlist the vision agent parsed
    from the breadboard photo; the user can fix wires, parts, and labels in a desktop
    window before approving.

    Returns one of:
      {"status": "approved", "netlist": {...}}  — the user-corrected, trusted netlist
      {"status": "cancelled"}                    — the user closed without approving
      {"status": "error", "error": "..."}        — the input netlist was malformed

    Only an "approved" result should be treated as ground-truth topology.
    """
    try:
        normalized = schema.to_dict(schema.from_dict(netlist))
    except schema.NetlistError as e:
        return {"status": "error", "error": str(e)}

    with tempfile.NamedTemporaryFile("r", suffix=".json", delete=False) as f:
        out_path = f.name
    try:
        subprocess.run(
            [sys.executable, str(WINDOW), out_path],
            input=json.dumps(normalized),
            text=True,
            check=True,
        )
        result = json.loads(pathlib.Path(out_path).read_text())
    finally:
        pathlib.Path(out_path).unlink(missing_ok=True)

    if result.get("status") == "approved":
        # Re-validate the user's edits before handing them to the chat.
        try:
            result["netlist"] = schema.to_dict(schema.from_dict(result["netlist"]))
        except schema.NetlistError as e:
            return {"status": "error", "error": f"corrected netlist invalid: {e}"}
    return result


if __name__ == "__main__":
    mcp.run()
