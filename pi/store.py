"""
store.py — Redis session state (optional layer).

If Redis is unavailable, all functions are no-ops and the lesson continues
with in-memory state. Never import this at module level in critical paths.
"""

import json
from config import REDIS_URL

_redis = None
_available = False


def _get_redis():
    global _redis, _available
    if _redis is not None:
        return _redis
    try:
        import redis
        r = redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=2)
        r.ping()
        _redis = r
        _available = True
        print("[store] Redis connected")
    except Exception as e:
        print(f"[store] Redis unavailable ({e}) — running without persistence")
        _redis = None
        _available = False
    return _redis


def save_step(session_id: str, step_index: int) -> None:
    r = _get_redis()
    if r:
        r.set(f"session:{session_id}:step", step_index, ex=86400)


def load_step(session_id: str) -> int:
    r = _get_redis()
    if r:
        val = r.get(f"session:{session_id}:step")
        if val is not None:
            return int(val)
    return 0


def save_history(session_id: str, history: list) -> None:
    r = _get_redis()
    if r:
        r.set(f"session:{session_id}:history", json.dumps(history), ex=86400)


def load_history(session_id: str) -> list:
    r = _get_redis()
    if r:
        val = r.get(f"session:{session_id}:history")
        if val:
            return json.loads(val)
    return []


def is_available() -> bool:
    _get_redis()
    return _available
