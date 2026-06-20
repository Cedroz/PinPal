"""
vision.py — crop a frame to a step's ROI, send to Claude vision, return verdict.

Standalone usage:
  python vision.py --step 0     poll step 0 every 2s and print YES/NO/UNSURE
"""

import argparse
import base64
import time
from enum import Enum

import cv2
import anthropic

from config import CLAUDE_VISION_MODEL, VISION_POLL_INTERVAL_S, VISION_CONFIRM_COUNT
from camera import open_camera, grab_frame, crop_roi


class Verdict(Enum):
    YES = "YES"
    NO = "NO"
    UNSURE = "UNSURE"


_client = None

def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def _encode_frame(frame) -> str:
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return base64.standard_b64encode(buf.tobytes()).decode("utf-8")


def check_step(frame, step: dict) -> Verdict:
    """Crop frame to step ROI, ask Claude the step's check question, return verdict."""
    roi_frame = crop_roi(frame, step["roi"])
    b64 = _encode_frame(roi_frame)

    client = _get_client()
    response = client.messages.create(
        model=CLAUDE_VISION_MODEL,
        max_tokens=16,
        system=(
            "You are a circuit inspection assistant. "
            "Answer the user's question about the image with exactly one word: "
            "YES, NO, or UNSURE. Output nothing else."
        ),
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": step["check_q"]},
                ],
            }
        ],
    )

    raw = response.content[0].text.strip().upper()
    if "YES" in raw:
        return Verdict.YES
    if "NO" in raw:
        return Verdict.NO
    return Verdict.UNSURE


def confirm_step(cap, step: dict, on_verdict=None) -> bool:
    """
    Poll until VISION_CONFIRM_COUNT consecutive YES verdicts.
    Returns True when confirmed, False never (caller decides when to give up).
    on_verdict(verdict) called each poll for logging/UI.
    """
    streak = 0
    while True:
        frame = grab_frame(cap)
        verdict = check_step(frame, step)
        if on_verdict:
            on_verdict(verdict)
        if verdict == Verdict.YES:
            streak += 1
            if streak >= VISION_CONFIRM_COUNT:
                return True
        else:
            streak = 0
        time.sleep(VISION_POLL_INTERVAL_S)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", type=int, default=0, help="Step index (0-based)")
    args = parser.parse_args()

    from lessons.light_led import STEPS
    step = STEPS[args.step]
    print(f"Polling step {args.step}: {step['id']}")
    print(f"ROI: {step['roi']}  |  Question: {step['check_q'][:60]}...")

    cap = open_camera()
    try:
        while True:
            frame = grab_frame(cap)
            verdict = check_step(frame, step)
            print(f"  {time.strftime('%H:%M:%S')}  {verdict.value}")
            time.sleep(VISION_POLL_INTERVAL_S)
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
