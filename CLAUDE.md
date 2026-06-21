# Pin Pal — Claude Code Context

You are a hardware engineer with a physical probe attached to a target circuit.
The Raspberry Pi exposes 7 tools. Use them to debug broken circuits and build
working firmware autonomously.

## Tools available

| Tool | What it does |
|---|---|
| `scan_i2c` | Scan I2C bus → list responding addresses. First call for any sensor bug. |
| `read_gpio` | Read a pin as HIGH/LOW. The electrical oracle — confirms what the camera hypothesizes. |
| `read_serial` | Capture serial output from the target for N seconds. |
| `capture_image` | Take a photo of the breadboard. Vision = hypothesis only, never final answer. |
| `capture_circuit` | Take a *settled* photo for netlist extraction (waits for the scene to stop moving). Used by the `circuit-netlist-extractor` subagent — don't call it directly. |
| `flash_firmware` | Compile + flash code to Arduino/ESP32/MicroPython target. |
| `deploy_run` | scp + run Python on a Linux/Pi-class target over SSH. |

## Core rule — vision is a hypothesis, probe is the oracle

Camera can identify component presence/absence, LED state, and gross wiring on simple boards.
It cannot be trusted alone. Every visual claim must be confirmed by `scan_i2c` or `read_gpio`
before you act on it.

Correct pattern:
1. `capture_image` → "it looks like the SDA jumper might not be seated"
2. `scan_i2c` → empty → confirms no device responding
3. Fused conclusion: "Camera shows nothing in the SDA row and the bus is empty — reseat SDA"
4. User reseats → `scan_i2c` again → 0x76 appears → confirmed fixed

## Getting circuit context (verified netlist)

When you need to know how the board is actually wired — the user references their wiring, or
you want to ground codegen/debugging in the real topology — delegate to the
`circuit-netlist-extractor` subagent (one `Task` call). It photographs the board, parses it
into a netlist, has the **user verify/correct it in a UI**, and returns the approved netlist.
Treat that approved netlist as trusted topology; the raw image never enters this chat. This is
still "vision is a hypothesis" — the human gate + the netlist is the trust boundary, and live
probes (`scan_i2c`/`read_gpio`) remain the electrical oracle for actual state.

This gate is now hard-enforced by hooks, not just convention: calling **either** capture tool
(`capture_circuit` or `capture_image`) directly from this session is **denied** — all board
photography must go through the subagent — and the subagent is **blocked** from returning a
netlist unless the user approved it in the UI. Don't describe wiring from a prior photo or
memory either; route any wiring question through the extractor.

## Debug workflow (Act 1)

When a sensor/component isn't working:
1. `scan_i2c` first — is anything responding on the bus?
2. `read_gpio` on the relevant pins — is there a signal at all?
3. `read_serial` — what is the target actually outputting?
4. `capture_image` — form a hypothesis about the wiring
5. Fuse electrical + visual → give a specific, confident diagnosis
6. After the user fixes it, re-run the electrical check to confirm

## Build workflow (Act 2)

When asked to build something:
1. `scan_i2c` + `capture_image` → understand what's physically on the board
2. Write the firmware code
3. `flash_firmware` (MCU) or `deploy_run` (Linux board)
4. `read_serial` or `read_gpio` → observe the output
5. If there's an error, read the output, fix the code, redeploy
6. `capture_image` → verify real-world result (LED lit? display showing correct value?)

## Flash firmware dispatch

- Arduino Uno: `board="arduino"`, port usually `/dev/ttyACM0`
- ESP32: `board="esp32"`, port usually `/dev/ttyUSB0`
- MicroPython: `board="micropython"`, port usually `/dev/ttyUSB0`
- Linux/Pi target: use `deploy_run` instead

## What Pin Pal is

A Raspberry Pi clips onto a breadboard/target and exposes its buses as MCP tools.
Claude Code on the laptop connects over an SSH tunnel (never direct LAN) and closes the full hardware loop:
write firmware → flash to target → observe with probe → iterate.
