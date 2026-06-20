"""
voice.py — Deepgram TTS (speak) + STT (listen) for Pi/Linux.

Standalone usage:
  python voice.py --speak "Hello world"
  python voice.py --listen
"""

import argparse
import os
import queue
import subprocess
import tempfile
import time

import pyaudio
from deepgram import DeepgramClient, SpeakOptions, LiveTranscriptionEvents, LiveOptions

from config import DEEPGRAM_API_KEY

_dg = None

def _get_dg() -> DeepgramClient:
    global _dg
    if _dg is None:
        _dg = DeepgramClient(DEEPGRAM_API_KEY)
    return _dg


# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------

def speak(text: str) -> None:
    """Synthesize text and play through the default audio output."""
    dg = _get_dg()
    options = SpeakOptions(model="aura-asteria-en")

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        tmp_path = f.name

    try:
        dg.speak.v("1").save(tmp_path, {"text": text}, options)
        _play_audio(tmp_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def _play_audio(path: str) -> None:
    """Play an mp3 file on Linux/Pi using available system player."""
    for player in ["mpg123", "ffplay"]:
        if _cmd_exists(player):
            if player == "mpg123":
                subprocess.run(["mpg123", "-q", path], check=True)
            elif player == "ffplay":
                subprocess.run(
                    ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path],
                    check=True,
                )
            return
    print("[voice] No audio player found — install mpg123: sudo apt-get install mpg123")


def _cmd_exists(cmd: str) -> bool:
    return subprocess.run(["which", cmd], capture_output=True).returncode == 0


# ---------------------------------------------------------------------------
# STT
# ---------------------------------------------------------------------------

def listen(timeout_s: float = 8.0) -> str:
    """Record from mic for up to timeout_s, return Deepgram transcript."""
    dg = _get_dg()
    result_q: queue.Queue[str] = queue.Queue()
    parts: list[str] = []

    def on_message(self, result, **kwargs):
        sentence = result.channel.alternatives[0].transcript
        if sentence and result.is_final:
            parts.append(sentence)

    def on_close(self, close, **kwargs):
        result_q.put(" ".join(parts))

    options = LiveOptions(
        model="nova-3",
        language="en-US",
        smart_format=True,
        endpointing=500,
    )

    connection = dg.listen.live.v("1")
    connection.on(LiveTranscriptionEvents.Transcript, on_message)
    connection.on(LiveTranscriptionEvents.Close, on_close)
    connection.start(options)

    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000,
                    input=True, frames_per_buffer=1024)

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        data = stream.read(1024, exception_on_overflow=False)
        connection.send(data)

    stream.stop_stream()
    stream.close()
    p.terminate()
    connection.finish()

    try:
        return result_q.get(timeout=5.0)
    except queue.Empty:
        return " ".join(parts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--speak", type=str)
    parser.add_argument("--listen", action="store_true")
    args = parser.parse_args()

    if args.speak:
        print(f"Speaking: {args.speak}")
        speak(args.speak)
    elif args.listen:
        print("Listening for 8 seconds...")
        print(f"Transcript: {listen(8.0)!r}")
