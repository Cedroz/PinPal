# Build Plan — Pin Pal

*A hardware dev environment for Claude Code.* A Raspberry Pi clips onto your breadboard,
exposes the target's I2C / UART / GPIO / camera as MCP tools, and flashes firmware to it —
so Claude Code on your laptop can **debug** and **build** physical hardware projects over the LAN.

## Context

Berkeley AI Hackathon project. A Raspberry Pi acts as a **universal hardware probe + programmer**
for a *separate* target (Arduino / ESP32 / MicroPython board / breadboard). The Pi exposes the
target's buses and camera as **MCP tools** and can **flash firmware** to it; Claude Code runs on
the developer's laptop and connects over the LAN. This plan gives everything needed to start
building — tool signatures, Pi setup, wiring, the laptop connection config, and a two-act demo —
while avoiding the failure trap of "just Claude Code with a shell."

The product is not only a debugger. Because the probe gives Claude *senses* and `flash_firmware`
gives it *reach*, Claude can close the full agentic loop on hardware:

```
write firmware  →  flash to target  →  observe with the probe  →  iterate
```

### Decisions locked (from this session)
- **Name:** **Pin Pal.**
- **Transport:** HTTP/SSE MCP server on the Pi; laptop connects over LAN.
- **Voltage sensing:** **Digital-only** — no ADC. `read_gpio` reports logic HIGH/LOW
  (3.3V threshold) only. **Pitch line:** *"your code drives GPIO17 HIGH, the probe on that
  pin reads LOW, and the camera shows the jumper isn't seated — your wire fell out."*
  Same fusion wow, honest about the hardware. (ADS1115 ADC = clean v2 upgrade for true voltage.)
- **Scope:** **Full build loop** — read tools (sense) + write tools (reach). Two-act demo: debug + build.
- **Target families:** support **both MCUs and Linux boards.** `flash_firmware` for
  Arduino/ESP32/MicroPython (compile + upload); `deploy_run` for Pi-class Linux targets
  (scp the code + ssh run). Sensing works on every target regardless. Pick the specific board(s)
  when hardware is in hand; backends dispatch on board/target type.
- **Camera role:** vision is a **hypothesis generator, never an oracle.** A VLM can read binary
  state (LED lit, display content) and gross presence/absence reliably, and can attempt wiring
  reads on *simple* boards — but it fails *confidently* on dense ones. So every visual claim is
  **gated behind an electrical/behavioral check** (the probe is the oracle: "camera guessed,
  `scan_i2c` confirmed"). Camera also serves as the build-loop **output verifier** (did the LED
  actually light / the display actually show the value?). Analyzer is the multimodal model itself
  (no custom CV); optional cheap assists = pixel-brightness sampling + before/after frame diff.
- **Vision spike first:** before committing the camera's reach, empirically test the VLM on ~10
  representative breadboard photos (sparse↔dense, varied lighting) and calibrate from data.
- **Netlist pipeline + human gate:** the camera feed becomes context as a *verified netlist*, not
  raw pixels — parsed by a dedicated vision agent, confirmed by the user in a UI, and only then
  pulled into the chat. See "Netlist pipeline" below. Sim integration deferred (stretch).

---

## Architecture

```
Laptop (Claude Code) ──HTTP/SSE over LAN──> Pi MCP server "pin-pal" (FastMCP, :8000)
                                                  │
                ┌─────────────┬──────────────┬────┴────────┬──────────────┐
             I2C bus      GPIO (digital)   Pi Camera    USB-serial   flash / deploy
            (smbus2)    (gpiozero/lgpio)  (picamera2)   (pyserial)   (arduino-cli/esptool/
                │             │               │             │         mpremote | scp+ssh)
                └─────────────┴──────── clipped onto TARGET ┴─────────────┘
              (Arduino / ESP32 / MicroPython MCU  —or—  Pi-class Linux board)
```

The Pi is both probe (read) and programmer (write). Claude reasons on the laptop and calls tools
to sense the target, flash it, and watch the result.

### What runs where (the boundary)
- **MCP server runs ONLY on the Raspberry Pi — that Pi *is* Pin Pal.** It needs full Linux,
  networking, Python, and the flash toolchains; a microcontroller cannot host it. Pin Pal is the
  single device we build and configure, reused across every project.
- **The user's microcontroller is the "target" and runs nothing of ours.** Pin Pal reaches it via
  **USB** (flashing) and **probe jumpers** (I2C/UART/GPIO sensing). The only code that lands on the
  target is the firmware Claude writes and Pin Pal flashes — the user's own project code.
- **The user installs nothing on their board.** Plug Pin Pal in, point Claude Code at it.
- **Sensing is universal; flashing is per-toolchain.** I2C/UART/GPIO probing needs no per-board code,
  so debugging works on any target. `flash_firmware` needs a backend per board toolchain
  (arduino-cli / esptool / mpremote) — hence the `board` dispatch argument.

---

## Netlist pipeline (vision → verified context)

Turns the camera feed into trustworthy *structured* context for the chat, with a human gate so no
hallucinated wiring ever reaches the model. Everything except the final pull runs in a **companion
service + web UI, OUTSIDE the chat turn.**

```
Pi capture daemon ─► vision→netlist agent ─► verification UI ─► approval ─► [chat pulls it]
 (change-triggered)    (Claude API, JSON)     (render+edit)     (user OK)   get_confirmed_netlist()
```

1. **Change-triggered capture (Pi):** frame-diff loop; on a significant change, **wait for the
   scene to settle** (N stable frames) then grab one clean keyframe. Avoids parsing blurry
   hands-in-frame shots. Reuses the before/after diff assist from the camera tooling.
2. **Vision→netlist agent:** the keyframe goes to a dedicated multimodal Claude agent (via the
   Claude API in the companion service) whose only job is image→structured netlist JSON. Isolated
   so raw images and vision-reasoning never clog the main chat context.
3. **Verification UI (web):** renders the netlist (component/net graph) for the user to confirm or
   correct. Stretch: export to **ngspice** (SPICE decks *are* netlists, so the export is near-native)
   and a button to let Claude Code run the deck and check it behaves as intended.
4. **Approval gate:** only a user-approved netlist is published to the approved-netlist store.
5. **Into context (pull, not push):** the chat gains the netlist when Claude calls
   `get_confirmed_netlist()` — the tool only ever returns approved data, so **the gate is enforced
   by construction.** MCP is pull-based; "streaming into the chat" = the companion pipeline does the
   work and the chat reads the approved result. The raw image need never enter the chat.

**How it ties together:** this verified netlist is the **topology layer** of the board model; the
electrical probes supply **live state** and remain the ground-truth oracle. That yields **two
verification oracles** — *ngspice simulation* (does the design work in theory: real node voltages)
and *physical probes* (does the build work in reality). Comparing them localizes faults: "ngspice
expects 5V on D13, board reads 0V → physical fault, not a design bug." SPICE's numeric node voltages
are directly comparable to probe readings, which is why ngspice (not a visual sim) is the target.

**Scope:** MVP = the spine (capture → parse → UI render → approve → `get_confirmed_netlist`).
ngspice export + Claude-drives-the-sim = explicit stretch. The companion service/UI is a separate
component from the Pi MCP probe server.

## Hardware / Bill of materials
- Raspberry Pi (4 or 5; Zero 2 W works) with Pi OS Bookworm, on the same LAN as the laptop.
- Pi Camera Module on a gooseneck/arm pointed at the breadboard.
- Female–female + female–male jumper wires (probe leads: Pi header → target SDA/SCL/TX/RX/GND/3V3).
- Target board for the demo (e.g. ESP32 / Arduino + an I2C sensor such as BME280 @ `0x76`),
  connected to the Pi by **USB** (this is the flashing path) and by probe jumpers (the sensing path).
- Optional v2: ADS1115 I2C ADC for true analog voltage.

### Wiring
- I2C: Pi `GPIO2 (SDA)` / `GPIO3 (SCL)` → target SDA/SCL; common **GND**.
- GPIO sense: any free Pi GPIO as **input** clipped to the target pin under test; **shared GND mandatory**.
- UART observe: USB-serial into the Pi (`/dev/ttyUSB0` / `/dev/ttyACM0`), keeps the Pi console UART free.
- Flash: target's USB cable into the Pi.

---

## Pi setup
1. `sudo raspi-config` → enable **I2C**, **Camera**, **Serial hardware** (disable serial *login shell*).
2. System deps: `sudo apt install -y python3-picamera2 i2c-tools` (`i2c-tools` gives `i2cdetect`).
3. Build backends (install what matches the chosen target):
   - MCUs: `arduino-cli` (Arduino/ESP32 core), and/or `pip install esptool mpremote`.
   - Linux targets: ssh client (preinstalled) + a **key-based ssh login to the target**
     (`ssh-copy-id user@<target>`) so `deploy_run` can scp+run without a password prompt.
4. Project venv (system site packages so picamera2 is visible):
   `python3 -m venv --system-site-packages .venv && source .venv/bin/activate`
5. `pip install "mcp[cli]" smbus2 pyserial gpiozero lgpio`
6. Note the Pi's LAN IP (`hostname -I`) for the laptop config.

---

## MCP server — `pin_pal_server.py`

**FastMCP** (`from mcp.server.fastmcp import FastMCP`), streamable-HTTP transport bound to
`0.0.0.0:8000`. Every tool returns structured, Claude-readable results — catch failures and
return an `error` field (e.g. "bus busy", "no device", "compile failed: <stderr>") so Claude
can reason about them instead of seeing a traceback.

### How deployment physically works
Pin Pal has up to **three independent links** to the target — keep them distinct:
- **USB cable** → deploy/flash + power + serial console (`read_serial`). This is the deploy path.
- **Probe jumpers** → I2C/GPIO sensing.
- **Camera** → vision (no wire).

`flash_firmware` shells out to the vendor toolchain on Pin Pal, which talks to the MCU's
**bootloader** over the USB-serial port (`/dev/ttyUSB0`/`/dev/ttyACM0`):
- **Arduino:** arduino-cli compiles → avrdude toggles DTR to auto-reset into the bootloader → streams the hex.
- **ESP32/ESP8266:** esptool toggles DTR/RTS (wired to EN/GPIO0) → download mode → writes flash.
- **MicroPython:** no compile/flash — mpremote copies the `.py` over the serial REPL + soft-reset.

For Linux/Pi-class targets, `deploy_run` uses the network instead: scp the code + ssh-run it.
Assumes dev boards that ship with a bootloader (all Arduino/ESP boards do); a bare blank chip
would need a separate ISP programmer — out of scope.

### Read tools (sense) — also serve as "board context" for codegen
```python
mcp = FastMCP("pin-pal", host="0.0.0.0", port=8000)

@mcp.tool()
def scan_i2c(bus: int = 1) -> dict:
    """Scan an I2C bus; return responding 7-bit addresses (hex). First call for any
    'sensor not reading' bug — splits wiring vs. code. Also grounds codegen."""

@mcp.tool()
def read_serial(port: str = "/dev/ttyUSB0", baud: int = 9600, duration_s: float = 2.0) -> dict:
    """Capture serial bytes for duration_s. Returns decoded text + raw hex +
    'looks_like_garbage' heuristic (baud mismatch / swapped TX-RX). Also the
    primary way to observe a freshly-flashed sketch's output."""

@mcp.tool()
def read_gpio(pin: int) -> dict:
    """Read one GPIO as digital HIGH/LOW (BCM). {"pin":17,"level":"LOW","value":0}.
    Digital only — no voltage."""

@mcp.tool()
def capture_image(filename: str | None = None) -> dict:
    """Capture a still of the wiring from the Pi camera. Returns viewable image content
    (base64 / MCP ImageContent) so Claude SEES seating/orientation/loose jumpers and verifies
    real-world output (LED lit? display showing the value?). Vision = hypothesis, not oracle:
    pair any wiring claim with an electrical/behavioral check before acting on it.
    Optional assists (cheap, deterministic): pixel-brightness sampling for LED on/off, and
    before/after frame diff to highlight what physically changed."""
```

### Write tools (reach) — the build loop
Two deploy paths so Pin Pal builds on both MCUs and Linux boards. Both return full toolchain
output so Claude can read errors and fix the code — that closed loop with the read tools is the
agentic build story.

```python
@mcp.tool()
def flash_firmware(source: str, board: str, port: str = "/dev/ttyUSB0") -> dict:
    """MCU targets. Compile (if needed) and flash firmware, return success + full output.
    Dispatches on `board`:
      - arduino/esp32 (Arduino core): write `source` to a sketch, arduino-cli compile && upload
      - esp32 (esptool):              esptool.py write_flash for a prebuilt binary
      - micropython:                  mpremote cp main.py : + reset   (no compile step)
    On failure: {"ok": false, "stage": "compile"|"upload", "output": "<stderr>"}."""

@mcp.tool()
def deploy_run(source: str, host: str, entry: str = "main.py",
               run: bool = True) -> dict:
    """Linux/Pi-class targets. scp `source` to `host` (key-based ssh) and, if run=True,
    execute it (e.g. `python3 entry`), returning stdout/stderr + exit code. No compile/flash —
    Linux boards run code directly. On failure return the captured stderr so Claude can fix it."""
```

Notes:
- `capture_image` must return **viewable** image content, not just a path — vision fusion depends on it.
- Keep read handlers sub-second (probe-loop latency is the make-or-break factor). `read_serial`
  is the only intentionally-blocking read (bounded by `duration_s`); `flash_firmware` is slow by
  nature — return progress/log text, don't hang silently.
- Run: `python pin_pal_server.py` (systemd unit optional, not needed for the demo).

---

## Laptop — connect Claude Code to Pin Pal

If your laptop and the Pi are on the **same LAN** and direct HTTP between them is reliable:
```bash
claude mcp add --transport http pin-pal http://<PI_LAN_IP>:8000/mcp
```

In practice (e.g. hackathon venue WiFi), laptops and the Pi often end up on **different
networks**, and direct HTTP between them can be unreliable or fully blocked even when SSH
isn't. For that case use the team scripts instead — they tunnel MCP traffic over SSH, which
has been the reliable path:

```bash
./scripts/pinpal_connect.sh      # one-time per teammate, safe to re-run
```
First run generates you a dedicated SSH key and prints it for the Pi's owner to authorize via
`./scripts/pinpal_authorize.sh "<your pubkey line>"`. After that it opens a self-healing SSH
tunnel (auto-reconnects on drop) and runs `claude mcp add` for you, pointed at the tunnel.

Verify with `/mcp` or `claude mcp list` — the six tools should list as Connected. Then
*"my BME280 isn't reading"* makes Claude call `scan_i2c` first; *"make the LED blink when the
sensor reads over 25°C"* drives the build loop (`flash_firmware` for an MCU target, `deploy_run`
for a Pi-class target).

---

## Demo — two acts on one rig

**Act 1 — Debug (deterministic, your safe anchor).**
Scripted miswire. User: "My sensor won't read." → `scan_i2c` empty → `read_gpio`/`read_serial`
confirms no signal → `capture_image` *hypothesizes* the loose/misrouted jumper → **probe confirms
the hypothesis** (the camera guessed, `scan_i2c`/`read_gpio` is the oracle) → **fused conclusion**:
"Code drives GPIO17 HIGH but the probe reads LOW and the camera shows nothing seated in that row —
reseat your SDA jumper." → reseat → re-`scan_i2c` → `0x76` appears. No single tool produces that
conclusion, and vision is never trusted without electrical confirmation.

**Act 2 — Build (the vibe-code wow).**
User: "Read the sensor and blink the LED when it's warm." → Claude calls `scan_i2c`/`capture_image`
for board context → writes the code → deploys it (`flash_firmware` for an MCU target, `deploy_run`
for a Pi-class target) → (let one compile/runtime error surface so Claude reads the output and
auto-fixes) → redeploy → `read_serial`/`read_gpio`/`capture_image` confirm it runs. Hardware built
and verified live, hands-free.

Act 1 is the reliable fallback if Act 2's flash/compile misbehaves.

---

## Build phasing (hackathon time budget)
0. **Vision spike (~20 min, do first)** → feed Claude ~10 representative breadboard photos (sparse↔dense, varied lighting) and measure where wiring analysis breaks. → verify: documented confidence boundary that sets how far the camera is allowed to reach before the probe must confirm.
1. **Skeleton + transport** → verify: laptop `/mcp` lists tools; a ping-style tool returns. *(de-risk network first)*
2. **`scan_i2c`** → verify: matches `i2cdetect -y 1`.
3. **`capture_image`** → verify: Claude describes the wiring from the returned image.
4. **`read_gpio`** → verify: toggling target pin flips HIGH/LOW.
5. **`read_serial`** → verify: clean text at right baud, garbage flag at wrong baud.
6. **Build path for your demo target** → MCU: `flash_firmware` flashes a hello-world blink and runs; force a compile error and confirm the error text comes back. Linux: `deploy_run` scp+runs a blink script and returns stdout/exit code; force a Python error and confirm stderr comes back.
7. **Script Act 1 + rehearse both acts** end-to-end ≥3×.

---

## Verification
- **Per tool (on Pi):** cross-check against native CLIs — `scan_i2c` vs `i2cdetect -y 1`;
  `read_gpio` vs a known drive; `read_serial` vs `minicom`; `flash_firmware` vs a manual
  `arduino-cli upload` / `mpremote`; `deploy_run` vs a manual `scp` + `ssh python3`.
- **End-to-end (from laptop):** in Claude Code, run the Act 1 prompt (autonomous
  scan→gpio/serial→image→diagnosis→re-scan) and the Act 2 prompt (context→write→flash→observe→iterate).
- **Latency:** time each read round-trip; flag anything >1s except `read_serial`/`flash_firmware`.
- **Failure modes to rehearse:** Wi-Fi drop / Pi IP change (fallback hotspot), bus-busy,
  camera-in-use, **compile failure** (should return clean error text Claude can fix from), upload
  port busy. Each tool returns a clean `error`, never crashes the server.

## Out of scope (v2)
ADS1115 ADC for true voltage; mic/voice; Pi-driven outputs (`write_gpio` to toggle a relay
directly); web dashboard; multi-target probing.
