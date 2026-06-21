#!/usr/bin/env bash
# Claude Code SubagentStop hook: enforce the human-in-the-loop netlist gate.
#
# Registered at project scope in .claude/settings.json. Fires when ANY subagent
# stops (SubagentStop has no matcher), so it scopes itself by `agent_type`. It is
# a no-op unless the just-finished circuit-netlist-extractor subagent called
# mcp__pin-pal__capture_circuit. If it did, the subagent must also hold an
# *approved* (or user-*cancelled*) mcp__pin-pal-ui__confirm_netlist tool_result —
# otherwise the stop is BLOCKED and the subagent is told to run the UI gate. This
# guarantees no parsed netlist reaches the parent context without the user
# reviewing/approving it.
#
# Key detail: SubagentStop input carries TWO transcript paths. `transcript_path`
# is the PARENT session (which does NOT contain the subagent's own tool calls),
# while `agent_transcript_path` is the subagent's own transcript. We must read the
# latter. (Earlier versions scoped by `isSidechain==true` over `transcript_path`;
# that flag is no longer set in current Claude Code transcripts, so the gate
# silently became a no-op. `agent_type` + `agent_transcript_path` are the
# supported, version-stable signals.)
#
# Fails open (allows the stop) on any infra error so a transcript hiccup can't
# brick every subagent, including unrelated ones (Explore, etc.).

set -u

INPUT="$(cat)"

python3 - "$INPUT" <<'PY'
import json, sys

EXTRACTOR = "circuit-netlist-extractor"

try:
    inp = json.loads(sys.argv[1])
except Exception:
    sys.exit(0)  # can't parse hook input -> fail open

# Loop guard: if we already blocked once, let it stop.
if inp.get("stop_hook_active"):
    sys.exit(0)

# Only the netlist extractor is gated; any other subagent is none of our business.
if inp.get("agent_type") != EXTRACTOR:
    sys.exit(0)

# The subagent's OWN transcript holds its capture_circuit / confirm_netlist calls.
# The parent `transcript_path` does not, so we must use agent_transcript_path.
path = inp.get("agent_transcript_path")
if not path:
    sys.exit(0)

try:
    with open(path) as f:
        lines = [json.loads(l) for l in f if l.strip()]
except Exception:
    sys.exit(0)  # unreadable transcript -> fail open


def content_items(e):
    c = e.get("message", {}).get("content")
    return c if isinstance(c, list) else []


captured = False
confirm_ids = set()
for e in lines:
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


# The user got to review iff confirm_netlist returned a terminal decision:
# "approved" (trusted netlist) or "cancelled" (they saw it and declined). An
# "error" result means the UI never opened (malformed netlist) -> still block so
# the agent fixes it and re-gates.
reviewed = False
for e in lines:
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
        if isinstance(payload, dict) and payload.get("status") in ("approved", "cancelled"):
            reviewed = True

if reviewed:
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
