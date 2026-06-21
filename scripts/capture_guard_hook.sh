#!/usr/bin/env bash
# Claude Code PreToolUse hook (matchers: mcp__pin-pal__capture_circuit and
# mcp__pin-pal__capture_image).
#
# Registered at project scope in .claude/settings.json. Denies ANY board
# photography unless it originates from the circuit-netlist-extractor subagent
# (which gates the parsed netlist through the review UI). Both capture tools are
# gated: capture_image was an open side-door letting the main session describe
# wiring without the UI.
#
# Detection: Claude Code passes the calling agent identity in the hook input as
# `agent_type`. The main session has no such agent type (the field is absent or
# empty); a subagent carries its registered type. We allow ONLY when that type is
# exactly "circuit-netlist-extractor", and deny everything else.
#
# (Earlier versions sniffed transcript `isSidechain` flags; that field is no
# longer set to true in current Claude Code transcripts, which silently broke the
# gate — it denied the legitimate subagent too. `agent_type` is the supported,
# version-stable signal.)

set -u

INPUT="$(cat)"

python3 - "$INPUT" <<'PY'
import json, sys

EXTRACTOR = "circuit-netlist-extractor"

def allow():
    sys.exit(0)  # no output -> allow

def deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)

try:
    inp = json.loads(sys.argv[1])
except Exception:
    # Can't parse hook input -> we cannot confirm this is the extractor. The gate
    # is the whole point, so fail CLOSED on capture tools.
    deny(
        "Board photography is gated and the guard could not verify the caller. "
        "Capture must come from the circuit-netlist-extractor subagent. Delegate "
        "with the Task tool (subagent_type: circuit-netlist-extractor)."
    )

if inp.get("agent_type") == EXTRACTOR:
    allow()

deny(
    "Board photography is gated: capturing the breadboard is only allowed from the "
    "circuit-netlist-extractor subagent, because a circuit's wiring must never reach "
    "the main session until the user has reviewed and approved the netlist in the "
    "review UI. Delegate with the Task tool (subagent_type: circuit-netlist-extractor) "
    "— it photographs the board, parses a netlist, and runs the human-review gate. Do "
    "not describe the wiring from memory or a prior photo either; route it through the "
    "extractor."
)
PY
