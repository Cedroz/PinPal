"""
state.py — lesson state machine.

Drives steps in order: present instruction → poll vision → advance or correct.
Text-only mode (no voice) when speak/listen are None — for Phase 3 testing.
"""

import time
from dataclasses import dataclass, field
from enum import Enum, auto

from config import VISION_MAX_FAILS_BEFORE_HINT
from lessons.light_led import STEPS, total_steps
from vision import Verdict


class Phase(Enum):
    PRESENTING = auto()   # just spoke the instruction
    CHECKING = auto()     # polling vision
    CORRECTING = auto()   # gave a hint, waiting
    DONE = auto()


@dataclass
class LessonState:
    step_index: int = 0
    phase: Phase = Phase.PRESENTING
    fail_count: int = 0
    conversation_history: list = field(default_factory=list)


def run_lesson(
    cap,
    check_fn,        # (frame, step) -> Verdict
    speak_fn=None,   # str -> None  (None = print)
    listen_fn=None,  # () -> str    (None = no Q&A)
    correction_fn=None,   # (step, fail_count, kb_tip) -> str
    kb_lookup_fn=None,    # (step_id) -> str tip
    on_step_start=None,   # (step_index) -> None
    on_step_done=None,    # (step_index) -> None
) -> None:

    def say(text: str) -> None:
        if speak_fn:
            speak_fn(text)
        else:
            print(f"\n[TUTOR] {text}")

    state = LessonState()

    from camera import grab_frame

    while state.step_index < total_steps():
        step = STEPS[state.step_index]

        if state.phase == Phase.PRESENTING:
            if on_step_start:
                on_step_start(state.step_index)
            say(step["instruction"])
            state.phase = Phase.CHECKING
            state.fail_count = 0
            confirm_streak = 0
            continue

        if state.phase in (Phase.CHECKING, Phase.CORRECTING):
            frame = grab_frame(cap)

            # Non-blocking listen if available
            if listen_fn:
                transcript = listen_fn()
                if transcript and correction_fn:
                    from tutor import answer_question
                    answer = answer_question(transcript, step, state.conversation_history)
                    say(answer)

            verdict = check_fn(frame, step)
            print(f"  vision: {verdict.value}  (step {state.step_index+1}/{total_steps()})")

            if verdict == Verdict.YES:
                confirm_streak = getattr(state, "_streak", 0) + 1
                state._streak = confirm_streak
                if confirm_streak >= 2:
                    state._streak = 0
                    if on_step_done:
                        on_step_done(state.step_index)
                    say(f"Great, step {state.step_index + 1} looks good!")
                    state.step_index += 1
                    state.phase = Phase.PRESENTING
            else:
                state._streak = 0
                state.fail_count += 1
                if state.fail_count % VISION_MAX_FAILS_BEFORE_HINT == 0:
                    tip = ""
                    if kb_lookup_fn:
                        tip = kb_lookup_fn(step["id"])
                    if correction_fn:
                        hint = correction_fn(step, state.fail_count, tip)
                    else:
                        hint = f"Hmm, I'm not seeing it yet — double-check step {state.step_index + 1}."
                    say(hint)
                    state.phase = Phase.CORRECTING

            time.sleep(2.0)

    say("You did it! The LED is lit — you just built your first circuit!")
