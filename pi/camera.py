"""
camera.py — webcam capture and ROI cropping.

Standalone usage:
  python camera.py --preview          live preview to aim the rig
  python camera.py --capture          save a reference frame to reference/
"""

import argparse
import os
import time
import cv2
import numpy as np
from config import CAMERA_INDEX, FRAME_WIDTH, FRAME_HEIGHT, REFERENCE_DIR


def open_camera() -> cv2.VideoCapture:
    cap = cv2.VideoCapture(CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open camera index {CAMERA_INDEX}")
    return cap


def grab_frame(cap: cv2.VideoCapture) -> np.ndarray:
    ret, frame = cap.read()
    if not ret:
        raise RuntimeError("Failed to read frame from camera")
    return frame


def crop_roi(frame: np.ndarray, roi: tuple) -> np.ndarray:
    x, y, w, h = roi
    return frame[y : y + h, x : x + w]


def save_reference(frame: np.ndarray, name: str = "reference") -> str:
    os.makedirs(REFERENCE_DIR, exist_ok=True)
    path = os.path.join(REFERENCE_DIR, f"{name}.jpg")
    cv2.imwrite(path, frame)
    print(f"Saved reference frame: {path}")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true", help="Live preview")
    parser.add_argument("--capture", action="store_true", help="Save reference frame")
    args = parser.parse_args()

    cap = open_camera()
    print("Camera open. Press Q to quit, S to save a frame.")

    while True:
        frame = grab_frame(cap)

        cv2.imshow("HardwareTutor Camera", frame)
        key = cv2.waitKey(1) & 0xFF

        if key == ord("q"):
            break
        elif key == ord("s"):
            ts = int(time.time())
            save_reference(frame, name=f"ref_{ts}")

    cap.release()
    cv2.destroyAllWindows()
