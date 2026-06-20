"""
main.py — thin orchestration loop.

Modes:
  python main.py              full run with voice
  python main.py --no-voice   text-only (Phase 3 mode)
  python main.py --test-sentry  trigger a Sentry test error and exit
"""

import argparse
import uuid

import observability
observability.init()

from camera import open_camera
from vision import check_step
from tutor import introduce_step, correct_step, answer_question, celebrate_completion
from state import run_lesson
import store
import knowledge


def main():
    parser = argparse.ArgumentParser(description="HardwareTutor")
    parser.add_argument("--no-voice", action="store_true", help="Text-only mode (no mic/speaker)")
    parser.add_argument("--session", default=None, help="Resume a session ID")
    parser.add_argument("--test-sentry", action="store_true", help="Send test error to Sentry and exit")
    args = parser.parse_args()

    if args.test_sentry:
        observability.test_error()
        return

    session_id = args.session or str(uuid.uuid4())[:8]
    print(f"Session: {session_id}")

    # Build Redis knowledge index (no-op if Redis unavailable)
    knowledge.build_index()

    # Load persisted state if available
    start_step = store.load_step(session_id)
    history = store.load_history(session_id)
    if start_step > 0:
        print(f"Resuming from step {start_step + 1}")

    cap = open_camera()

    speak_fn = None
    listen_fn = None
    if not args.no_voice:
        from voice import speak, listen
        speak_fn = speak
        listen_fn = lambda: listen(timeout_s=0.5)  # non-blocking short poll

    def on_step_start(idx):
        store.save_step(session_id, idx)

    def on_step_done(idx):
        store.save_step(session_id, idx + 1)
        store.save_history(session_id, history)

    def correction_fn(step, fail_count, kb_tip=""):
        return correct_step(step, fail_count, kb_tip)

    def kb_lookup(step_id):
        return knowledge.lookup_tip(step_id)

    try:
        run_lesson(
            cap=cap,
            check_fn=check_step,
            speak_fn=speak_fn,
            listen_fn=listen_fn,
            correction_fn=correction_fn,
            kb_lookup_fn=kb_lookup,
            on_step_start=on_step_start,
            on_step_done=on_step_done,
        )
        if speak_fn:
            speak_fn(celebrate_completion())
        else:
            print(f"\n[TUTOR] {celebrate_completion()}")
    except KeyboardInterrupt:
        print("\nSession paused. Resume with --session", session_id)
    finally:
        cap.release()


if __name__ == "__main__":
    main()
