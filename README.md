# Pin Pal

A Raspberry Pi that clips onto a breadboard and gives Claude Code real hardware senses —
I2C, GPIO, serial, and a camera — plus the ability to flash firmware and run code on a
target board. You talk to Claude Code on your own laptop; it calls out to the Pi to look at
and act on whatever's wired up.

This doc is the practical "how do I actually use this" guide. For the full design rationale
(why vision is never trusted alone, the netlist pipeline, etc.) see `app/PIN_PAL.md`.

## What works right now

- The Pi (hostname `pinpal`) is already running, with all 6 tools live: `scan_i2c`,
  `read_gpio`, `read_serial`, `capture_image`, `flash_firmware`, `deploy_run`.
- The camera works and is verified.
- **No target board or sensor is wired up by default.** Until you connect one, `scan_i2c`
  will report an empty bus and `read_serial`/`flash_firmware` have nothing to talk to —
  that's expected, not broken. `capture_image` and basic GPIO reads still work with no
  target attached.
- `flash_firmware`'s toolchains (`arduino-cli`, `esptool`, `mpremote`) aren't installed on
  the Pi yet — that happens whenever someone first needs to flash an actual board.
- The netlist/web-verification UI (a teammate's separate companion service) is **not**
  merged into `main` yet and isn't part of this flow.

## 1. Connect Claude Code to the Pi

You need: this repo cloned, `git`/`ssh` available, and Claude Code installed.

```bash
./scripts/pinpal_connect.sh
```

**First time only:** this will fail and print a public key line. Send that line to whoever
manages the Pi. On **their own laptop** (not on the Pi itself — the script SSHs into the Pi
remotely, it doesn't run there), they run:

```bash
./scripts/pinpal_authorize.sh "<the line you were sent>"
```

Then re-run `./scripts/pinpal_connect.sh` yourself. It should now succeed: it opens a
self-healing SSH tunnel (auto-reconnects if it drops) and registers the Pi with Claude Code
automatically. You won't need to repeat this step again on this machine.

Connection is **always over the SSH tunnel** — never a direct LAN/HTTP connection to the Pi.
The tunnel forwards a local port to the Pi's `:8000`, so Claude Code talks to `localhost`
and SSH carries the traffic (works across networks, encrypted, and survives WiFi drops).

## 2. Start a fresh Claude Code session

MCP connections are only picked up when a session starts — if you had Claude Code open
*before* running the connect script, close it and start a new session now.

Verify it worked:
```bash
claude mcp list
```
You should see `pin-pal ... ✔ Connected`.

## 3. Try it

Just talk to Claude Code in plain English — it decides which tool to call.

- **"Take a picture of the breadboard"** → calls `capture_image`, returns a real photo from
  the Pi's camera.
- **"Is anything on the I2C bus?"** → calls `scan_i2c`. With nothing wired up, expect an
  empty list — that's correct, not an error.
- **"Read GPIO pin 17"** → calls `read_gpio`, reports HIGH/LOW.
- **"My sensor isn't reading anything"** (once you have one wired up) → Claude scans the
  bus, checks the relevant pins, looks at a photo, and gives you a single diagnosis instead
  of just one tool's output.
- **"Flash this code to the Arduino and check the serial output"** (once a board is
  plugged in via USB) → drives the full write-then-observe loop.

## Known rough edges right now

- This session's tools won't reach the Pi until you've completed step 1 *and* started a
  fresh session (step 2) — reusing an old session is the most common reason "nothing
  happens."
- Captured images are never saved anywhere — each `capture_image` call returns the photo
  directly into that one conversation and nothing is persisted on the Pi or in this repo.
- No vision-reliability calibration ("vision spike") has been done yet, so there's no
  documented answer yet for how much to trust the camera on a dense/cluttered board —
  always treat a visual claim as a guess until `scan_i2c`/`read_gpio` confirms it.
