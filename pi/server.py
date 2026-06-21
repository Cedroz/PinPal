"""
pin_pal_server.py — MCP server exposing Pi hardware as tools.

Run on the Pi:
  python server.py

Connect from laptop:
  claude mcp add --transport http pin-pal http://<PI_LAN_IP>:8000/mcp
  Verify with /mcp — should list 2 tools (capture_image, capture_circuit).
"""

import base64
import os
import subprocess
import tempfile
import time

from mcp.server.fastmcp import FastMCP
from mcp.types import ImageContent

mcp = FastMCP("pin-pal", host="0.0.0.0", port=8000)


# ---------------------------------------------------------------------------
# READ TOOLS (sense)
# ---------------------------------------------------------------------------

# @mcp.tool()  # not exposed — only the capture tools are registered
def scan_i2c(bus: int = 1) -> dict:
    """
    Scan an I2C bus and return all responding 7-bit device addresses in hex.
    First call for any 'sensor not reading' bug — splits wiring vs. code.
    Also grounds Claude's codegen (confirms BME280 is at 0x76 not 0x77).
    Cross-check: should match `i2cdetect -y 1` output on the Pi.
    """
    try:
        import smbus2
        found = []
        with smbus2.SMBus(bus) as b:
            for addr in range(0x08, 0x78):
                try:
                    b.read_byte(addr)
                    found.append(hex(addr))
                except OSError:
                    pass
        return {"bus": bus, "devices": found, "count": len(found)}
    except Exception as e:
        return {"error": str(e), "hint": "Is I2C enabled? Run: sudo raspi-config → Interface Options → I2C"}


# @mcp.tool()  # not exposed — only the capture tools are registered
def read_gpio(pin: int) -> dict:
    """
    Read one GPIO pin as digital HIGH or LOW (BCM numbering).
    Digital only — no voltage. Use when the probe is clipped to a target pin.
    The probe is the oracle: always confirm camera wiring claims with this before acting.
    Example: camera guesses 'jumper seated', read_gpio confirms signal actually present.
    """
    try:
        from gpiozero import InputDevice
        device = InputDevice(pin)
        value = device.value
        device.close()
        return {"pin": pin, "level": "HIGH" if value else "LOW", "value": int(value)}
    except Exception as e:
        return {"error": str(e)}


# @mcp.tool()  # not exposed — only the capture tools are registered
def read_serial(
    port: str = "/dev/ttyUSB0",
    baud: int = 9600,
    duration_s: float = 2.0,
) -> dict:
    """
    Capture serial bytes from the target for duration_s seconds.
    Returns decoded text, raw hex, and a garbage flag (True = likely baud mismatch or swapped TX/RX).
    Primary way to observe a freshly-flashed sketch's Serial.println() output.
    Try /dev/ttyACM0 if /dev/ttyUSB0 is not found (Arduino Uno uses ACM).
    """
    try:
        import serial
        with serial.Serial(port, baud, timeout=1) as ser:
            start = time.time()
            chunks = []
            while time.time() - start < duration_s:
                waiting = ser.in_waiting
                if waiting:
                    chunks.append(ser.read(waiting))
                else:
                    time.sleep(0.05)
            raw = b"".join(chunks)
            text = raw.decode("utf-8", errors="replace")
            printable = sum(1 for c in text if c.isprintable() or c in "\n\r\t")
            garbage = len(text) > 10 and (printable / len(text)) < 0.7
            return {
                "port": port,
                "baud": baud,
                "text": text,
                "raw_hex": raw.hex(),
                "looks_like_garbage": garbage,
                "bytes_read": len(raw),
                "hint": "If looks_like_garbage=true, try flipping TX/RX or changing baud." if garbage else "",
            }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def capture_image(filename: str | None = None) -> list[ImageContent]:
    """
    Capture a still of the breadboard from the Pi Camera.
    Returns viewable image content so Claude can see wiring, component orientation,
    LED state, display output, and loose jumpers.
    IMPORTANT: Vision is a hypothesis generator, not an oracle.
    Always confirm any wiring claim by invoking the pin-pal-ui MCP (confirm_netlist)
    before acting on it.
    """
    try:
        from picamera2 import Picamera2
        cam = Picamera2()
        cam.configure(cam.create_still_configuration())
        cam.start()
        time.sleep(0.5)
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            tmp = f.name
        cam.capture_file(tmp)
        cam.stop()
        cam.close()
    except ImportError:
        # Fallback to OpenCV for testing on non-Pi hardware
        import cv2
        cap = cv2.VideoCapture(0)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            return {"error": "No camera found"}
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            tmp = f.name
        cv2.imwrite(tmp, frame)

    with open(tmp, "rb") as f:
        b64 = base64.standard_b64encode(f.read()).decode()
    os.remove(tmp)
    return [ImageContent(type="image", data=b64, mimeType="image/jpeg")]


@mcp.tool()
def capture_circuit(filename: str | None = None) -> list[ImageContent]:
    """
    Capture a clean, settled photo of the breadboard for NETLIST EXTRACTION.
    Unlike capture_image (a quick hypothesis snapshot), this waits for the scene to stop
    moving — it grabs frames until several consecutive frames are nearly identical, so it
    returns a sharp, hands-out-of-frame keyframe suitable for parsing wiring into a netlist.
    Falls back to the latest frame after ~3s so it never hangs.
    Returns viewable image content. This is the image the circuit-netlist-extractor reasons over.
    """
    import numpy as np

    SETTLE_FRAMES = 3        # consecutive stable frames required
    DIFF_THRESHOLD = 4.0     # mean abs per-pixel difference (0-255) considered "still"
    TIMEOUT_S = 3.0
    POLL_S = 0.1

    def _settle(grab) -> "np.ndarray":
        """grab() -> BGR/RGB frame as ndarray. Returns the first settled frame (or last on timeout)."""
        start = time.time()
        prev = grab()
        stable = 0
        while time.time() - start < TIMEOUT_S:
            time.sleep(POLL_S)
            cur = grab()
            diff = float(np.mean(np.abs(cur.astype("int16") - prev.astype("int16"))))
            prev = cur
            stable = stable + 1 if diff < DIFF_THRESHOLD else 0
            if stable >= SETTLE_FRAMES:
                break
        return prev

    try:
        from picamera2 import Picamera2
        cam = Picamera2()
        cam.configure(cam.create_still_configuration())
        cam.start()
        time.sleep(0.5)
        frame = _settle(cam.capture_array)
        cam.stop()
        cam.close()
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            tmp = f.name
        # picamera2 capture_array is RGB; cv2 writes BGR — convert so colors are correct.
        import cv2
        cv2.imwrite(tmp, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
    except ImportError:
        # Fallback to OpenCV for testing on non-Pi hardware
        import cv2
        cap = cv2.VideoCapture(0)

        def _grab():
            ret, f = cap.read()
            if not ret:
                raise RuntimeError("no frame")
            return f

        try:
            frame = _settle(_grab)
        except RuntimeError:
            cap.release()
            return [ImageContent(type="image", data="", mimeType="image/jpeg")]
        cap.release()
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            tmp = f.name
        cv2.imwrite(tmp, frame)

    with open(tmp, "rb") as f:
        b64 = base64.standard_b64encode(f.read()).decode()
    os.remove(tmp)
    return [ImageContent(type="image", data=b64, mimeType="image/jpeg")]


# ---------------------------------------------------------------------------
# WRITE TOOLS (reach)
# ---------------------------------------------------------------------------

# @mcp.tool()  # not exposed — only the capture tools are registered
def flash_firmware(
    source: str,
    board: str,
    port: str = "/dev/ttyUSB0",
) -> dict:
    """
    Compile (if needed) and flash firmware to an MCU target.
    Returns full toolchain output so Claude can read errors and fix the code autonomously.

    board values:
      'arduino'     — arduino-cli: compile .ino + upload via avrdude (Uno FQBN)
      'esp32'       — arduino-cli with ESP32 core
      'esptool'     — esptool.py write_flash for a prebuilt .bin binary
      'micropython' — mpremote cp main.py + soft-reset (no compile step)

    source: firmware source code (arduino/esp32/micropython) or path to .bin (esptool)
    On failure: {"ok": false, "stage": "compile"|"upload", "output": "<stderr>"}
    """
    board = board.lower().strip()
    try:
        if board in ("arduino", "esp32"):
            return _flash_arduino_cli(source, board, port)
        elif board == "esptool":
            return _flash_esptool(source, port)
        elif board == "micropython":
            return _flash_micropython(source, port)
        else:
            return {"ok": False, "error": f"Unknown board '{board}'. Use: arduino, esp32, esptool, micropython"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _flash_arduino_cli(source: str, board: str, port: str) -> dict:
    fqbn = "arduino:avr:uno" if board == "arduino" else "esp32:esp32:esp32"
    with tempfile.TemporaryDirectory() as d:
        sketch_name = os.path.basename(d)
        with open(os.path.join(d, f"{sketch_name}.ino"), "w") as f:
            f.write(source)
        compile_r = subprocess.run(
            ["arduino-cli", "compile", "--fqbn", fqbn, d],
            capture_output=True, text=True
        )
        if compile_r.returncode != 0:
            return {"ok": False, "stage": "compile", "output": compile_r.stderr}
        upload_r = subprocess.run(
            ["arduino-cli", "upload", "-p", port, "--fqbn", fqbn, d],
            capture_output=True, text=True
        )
        if upload_r.returncode != 0:
            return {"ok": False, "stage": "upload", "output": upload_r.stderr}
        return {"ok": True, "output": compile_r.stdout + upload_r.stdout}


def _flash_esptool(binary_path: str, port: str) -> dict:
    r = subprocess.run(
        ["esptool.py", "--port", port, "write_flash", "0x0", binary_path],
        capture_output=True, text=True
    )
    return {"ok": r.returncode == 0, "output": r.stdout + r.stderr}


def _flash_micropython(source: str, port: str) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
        f.write(source)
        tmp = f.name
    try:
        r = subprocess.run(
            ["mpremote", f"connect {port}", f"cp {tmp} :main.py", "reset"],
            capture_output=True, text=True
        )
        return {"ok": r.returncode == 0, "output": r.stdout + r.stderr}
    finally:
        os.remove(tmp)


# @mcp.tool()  # not exposed — only the capture tools are registered
def deploy_run(
    source: str,
    host: str,
    entry: str = "main.py",
    run: bool = True,
) -> dict:
    """
    Deploy Python code to a Linux/Pi-class target over SSH and optionally run it.
    Requires key-based SSH (no password): run ssh-copy-id user@<target> first.
    Returns stdout, stderr, and exit code so Claude can read errors and fix the code.

    source: Python source code to deploy
    host:   user@hostname or user@ip (e.g. pi@192.168.1.42)
    entry:  filename to save on the target (default: main.py)
    run:    if True, execute after copying
    """
    try:
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(source)
            tmp = f.name

        scp = subprocess.run(
            ["scp", "-o", "StrictHostKeyChecking=no", tmp, f"{host}:~/{entry}"],
            capture_output=True, text=True
        )
        os.remove(tmp)
        if scp.returncode != 0:
            return {"ok": False, "stage": "scp", "output": scp.stderr}

        if not run:
            return {"ok": True, "output": f"Deployed to {host}:~/{entry}"}

        ssh = subprocess.run(
            ["ssh", "-o", "StrictHostKeyChecking=no", host, f"python3 ~/{entry}"],
            capture_output=True, text=True, timeout=30
        )
        return {
            "ok": ssh.returncode == 0,
            "stdout": ssh.stdout,
            "stderr": ssh.stderr,
            "exit_code": ssh.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Remote process timed out after 30s"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
