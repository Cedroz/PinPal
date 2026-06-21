#!/usr/bin/env bash
# Claude Code SubagentStop hook: enforce the human-in-the-loop netlist gate.
#
# Registered at project scope in .claude/settings.json. Fires when ANY subagent
# stops (SubagentStop has no matcher), so it scopes itself by reading the
# transcript. It is a no-op unless the just-finished subagent called
# mcp__pin-pal__capture_circuit. If it did, the subagent must also hold an
# *approved* mcp__pin-pal-ui__confirm_netlist tool_result — otherwise the stop is
# BLOCKED and the subagent is told to run the UI gate. This guarantees no parsed
# netlist reaches the parent context without the user reviewing/approving it.
#
# Fails open (allows the stop) on any infra error so a transcript hiccup can't
# brick every subagent, including unrelated ones (Explore, etc.).

set -u

INPUT="$(cat)"

python3 - "$INPUT" <<'PY'
import json, sys

try:
    inp = json.loads(sys.argv[1])
except Exception:
    sys.exit(0)  # can't parse hook input -> fail open

# Loop guard: if we already blocked once, let it stop.
if inp.get("stop_hook_active"):
    sys.exit(0)

path = inp.get("transcript_path")
if not path:
    sys.exit(0)

try:
    with open(path) as f:
        lines = [json.loads(l) for l in f if l.strip()]
except Exception:
    sys.exit(0)  # unreadable transcript -> fail open

# Keep only real message lines (assistant/user with a message body).
msgs = [
    e for e in lines
    if e.get("type") in ("assistant", "user") and isinstance(e.get("message"), dict)
]

# Scope to THIS subagent: the maximal trailing contiguous run of isSidechain==true.
sub = []
for e in reversed(msgs):
    if e.get("isSidechain") is True:
        sub.append(e)
    else:
        break
sub.reverse()


def content_items(e):
    c = e.get("message", {}).get("content")
    return c if isinstance(c, list) else []


captured = False
confirm_ids = set()
for e in sub:
    for item in content_items(e):
        if item.get("type") == "tool_use":
            name = item.get("name")
            if name == "mcp__pin-pal__capture_circuit":
                captured = True
            elif name == "mcp__pin-pal-ui__confirm_netlist":
                confirm_ids.add(item.get("id"))

if not captured:
    sys.exit(0)  # not the netlist flow -> no-op


def result_text(item):
    c = item.get("content")
    if isinstance(c, list):
        return "".join(b.get("text", "") for b in c if b.get("type") == "text")
    if isinstance(c, str):
        return c
    return ""


approved = False
for e in sub:
    for item in content_items(e):
        if item.get("type") != "tool_result":
            continue
        if item.get("tool_use_id") not in confirm_ids:
            continue
        if item.get("is_error"):
            continue
        try:
            payload = json.loads(result_text(item))
        except Exception:
            continue
        if isinstance(payload, dict) and payload.get("status") == "approved":
            approved = True

if approved:
    sys.exit(0)

# Captured a circuit but no approved confirmation -> block the stop.
print(json.dumps({
    "decision": "block",
    "reason": (
        "Human-in-the-loop gate: you called capture_circuit and parsed a netlist, "
        "but the user has NOT approved it in the review UI. You MUST call "
        "mcp__pin-pal-ui__confirm_netlist(netlist=<your parsed JSON>) and receive a "
        "result with status \"approved\" before returning. If the user cancels, do "
        "NOT return a netlist as trusted topology — return the cancelled note "
        "instead. Run the gate now, then finish."
    ),
}))
sys.exit(0)
PY
