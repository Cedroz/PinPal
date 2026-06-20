"""
tutor.py — Claude dialogue: step instructions, corrections, Q&A answers.

All Claude calls here use text only (no vision). Vision lives in vision.py.
"""

import anthropic
from config import CLAUDE_MODEL

_client = None

def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


_SYSTEM = (
    "You are a warm, encouraging hardware tutor helping a beginner build their first "
    "LED circuit on a breadboard. Speak in plain language. Keep responses short — "
    "two or three sentences max. Never say the learner is wrong; express uncertainty "
    "gently (e.g. 'it looks like it might be...'). If they ask a question, answer it "
    "directly and simply."
)


def introduce_step(step: dict) -> str:
    """Return the step's instruction text directly — no Claude call needed."""
    return step["instruction"]


def correct_step(step: dict, fail_count: int, kb_tip: str = "") -> str:
    """Ask Claude to phrase a gentle correction for a failed vision check."""
    hint = f"\n\nRelated tip from our knowledge base: {kb_tip}" if kb_tip else ""
    prompt = (
        f"The learner is on step: '{step['id']}'.\n"
        f"Instruction given: {step['instruction']}\n"
        f"The camera check has failed {fail_count} time(s).{hint}\n\n"
        "Give a short, warm, uncertain correction — suggest what might be wrong "
        "without asserting it. Mention one specific thing to double-check."
    )
    response = _get_client().messages.create(
        model=CLAUDE_MODEL,
        max_tokens=120,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def answer_question(transcript: str, current_step: dict, history: list[dict]) -> str:
    """Answer a spoken question from the learner in context of the current step."""
    recent = history[-6:] if len(history) > 6 else history
    messages = recent + [
        {
            "role": "user",
            "content": (
                f"[Currently on step: {current_step['id']}]\n"
                f"Learner question: {transcript}"
            ),
        }
    ]
    response = _get_client().messages.create(
        model=CLAUDE_MODEL,
        max_tokens=150,
        system=_SYSTEM,
        messages=messages,
    )
    reply = response.content[0].text.strip()
    history.append({"role": "user", "content": transcript})
    history.append({"role": "assistant", "content": reply})
    return reply


def celebrate_completion() -> str:
    return (
        "The LED is lit! You just built your very first circuit — "
        "electricity is flowing from the power rail, through the resistor, "
        "through the LED, and back to ground. That's Ohm's Law in action. "
        "Great work!"
    )
