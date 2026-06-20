"""
observability.py — Sentry + Arize init (bolt-on, optional).

Import this once at the top of main.py. If keys are absent, it's a no-op.
"""

import functools
from config import SENTRY_DSN, ARIZE_API_KEY, ARIZE_SPACE_KEY

_sentry_ok = False
_arize_ok = False


def init() -> None:
    global _sentry_ok, _arize_ok
    _init_sentry()
    _init_arize()


def _init_sentry() -> None:
    global _sentry_ok
    if not SENTRY_DSN:
        print("[obs] Sentry DSN not set — skipping")
        return
    try:
        import sentry_sdk
        sentry_sdk.init(dsn=SENTRY_DSN, traces_sample_rate=1.0)
        _sentry_ok = True
        print("[obs] Sentry initialized")
    except Exception as e:
        print(f"[obs] Sentry init failed ({e})")


def _init_arize() -> None:
    global _arize_ok
    if not ARIZE_API_KEY:
        print("[obs] Arize key not set — skipping")
        return
    try:
        # Arize OpenTelemetry instrumentation
        from arize.otel import register
        register(
            space_key=ARIZE_SPACE_KEY,
            api_key=ARIZE_API_KEY,
            model_id="hwtutor-vision",
        )
        _arize_ok = True
        print("[obs] Arize initialized")
    except Exception as e:
        print(f"[obs] Arize init failed ({e})")


def capture_exception(exc: Exception) -> None:
    if _sentry_ok:
        import sentry_sdk
        sentry_sdk.capture_exception(exc)


def log_vision_check(step_id: str, question: str, verdict: str, ground_truth: str = "") -> None:
    """Log a vision check to Arize for eval tracking."""
    if not _arize_ok:
        return
    try:
        from opentelemetry import trace
        tracer = trace.get_tracer("hwtutor")
        with tracer.start_as_current_span("vision_check") as span:
            span.set_attribute("step_id", step_id)
            span.set_attribute("question", question)
            span.set_attribute("verdict", verdict)
            if ground_truth:
                span.set_attribute("ground_truth", ground_truth)
    except Exception:
        pass


def test_error() -> None:
    """Trigger a test error so you can verify Sentry is capturing."""
    try:
        raise ValueError("HardwareTutor test error — Sentry integration check")
    except ValueError as e:
        capture_exception(e)
        print("[obs] Test error sent to Sentry")
