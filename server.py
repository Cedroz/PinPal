"""
server.py — MCP server exposing Pi hardware as tools.

Claude Code connects to this and acts as the tutor brain.
Run on the Pi:  python server.py
Connect from laptop:
  claude mcp add hardware-tutor -- ssh pi@raspberrypi.local python /path/to/PinPal/server.py
  (or locally for testing)
  claude mcp add hardware-tutor -- python /mnt/c/Users/edwin/PinPal/server.py
"""

import base64
import cv2
from mcp.server.fastmcp import FastMCP
from mcp.types import ImageContent

from camera import open_camera, grab_frame
from voice import speak, listen

mcp = FastMCP("HardwareTutor")

_cap = None

def _get_cap():
    global _cap
    if _cap is None:
        _cap = open_camera()
    return _cap


@mcp.tool()
def get_camera_frame() -> list[ImageContent]:
    """
    Capture the current state of the breadboard from the overhead camera.
    Returns a JPEG image. Use this to visually assess whether the learner
    has completed a circuit-building step correctly.
    Call this every few seconds while waiting for a step to be completed.
    """
    cap = _get_cap()
    frame = grab_frame(cap)
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    b64 = base64.standard_b64encode(buf.tobytes()).decode()
    return [ImageContent(type="image", data=b64, mimeType="image/jpeg")]


@mcp.tool()
def speak_to_learner(text: str) -> str:
    """
    Speak text aloud to the learner through the Pi's speaker using TTS.
    Use this to give step instructions, gentle corrections, and answers to questions.
    Keep responses short, warm, and encouraging.
    Never assert the learner made a mistake — express uncertainty (e.g. 'it looks like
    the LED might be backwards — could you double check?').
    """
    speak(text)
    return "spoken"


@mcp.tool()
def listen_to_learner(timeout_seconds: float = 8.0) -> str:
    """
    Listen through the Pi's microphone for up to timeout_seconds and return
    the speech-to-text transcript. Use this to capture learner questions.
    Returns an empty string if nothing was heard.
    """
    transcript = listen(timeout_s=timeout_seconds)
    return transcript or ""


if __name__ == "__main__":
    mcp.run()
