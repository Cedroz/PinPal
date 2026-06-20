"""
knowledge.py — Redis vector KB of common beginner mistakes (optional layer).

Falls back to a simple keyword match if Redis vector search is unavailable.
"""

from config import REDIS_URL

MISTAKES = [
    {
        "id": "led_backwards",
        "step": "place_led",
        "tip": "The LED only works one way. The longer leg (anode) must go toward the positive rail. Try flipping it around.",
    },
    {
        "id": "led_wrong_gap",
        "step": "place_led",
        "tip": "The LED needs to bridge the center gap of the breadboard — one leg on each side of the gap.",
    },
    {
        "id": "resistor_missing",
        "step": "place_resistor",
        "tip": "Without the resistor the LED can burn out instantly. Make sure the striped cylinder is in the same row as the LED's long leg.",
    },
    {
        "id": "jumper_wrong_rail",
        "step": "jumper_power_to_resistor",
        "tip": "The red wire should go to the red plus rail, not the blue minus rail. Check which rail the wire is plugged into.",
    },
    {
        "id": "ground_missing",
        "step": "jumper_cathode_to_ground",
        "tip": "The circuit needs a complete loop. The short leg of the LED must connect back to the negative (blue) rail.",
    },
    {
        "id": "no_power",
        "step": "led_lit",
        "tip": "Make sure the power supply is switched on and the voltage is set to 5V or 3.3V.",
    },
    {
        "id": "loose_jumper",
        "step": "led_lit",
        "tip": "A loose jumper wire is the most common reason an LED won't light. Press each wire firmly into the breadboard.",
    },
]


_redis = None
_vector_ready = False
INDEX_NAME = "mistakes_idx"
EMBEDDING_DIM = 1536


def _get_redis():
    global _redis
    if _redis is not None:
        return _redis
    try:
        import redis
        r = redis.from_url(REDIS_URL, decode_responses=False, socket_connect_timeout=2)
        r.ping()
        _redis = r
    except Exception:
        _redis = None
    return _redis


def _embed(text: str) -> list[float]:
    import anthropic
    client = anthropic.Anthropic()
    # Claude doesn't have an embeddings endpoint; use a lightweight fallback.
    # For a real vector search, swap in OpenAI embeddings or sentence-transformers.
    # Here we use a bag-of-words hash as a placeholder so the pipeline works.
    import hashlib, struct
    h = hashlib.sha256(text.encode()).digest()
    # Expand to EMBEDDING_DIM floats deterministically
    vals = []
    for i in range(EMBEDDING_DIM):
        seed = h[(i * 2) % len(h)] * 256 + h[(i * 2 + 1) % len(h)]
        vals.append((seed / 65535.0) * 2 - 1)
    return vals


def build_index() -> None:
    """Load mistakes into Redis with vector embeddings. Run once at startup."""
    r = _get_redis()
    if not r:
        return
    try:
        from redis.commands.search.field import TextField, VectorField
        from redis.commands.search.indexDefinition import IndexDefinition, IndexType
        import numpy as np

        try:
            r.ft(INDEX_NAME).dropindex(delete_documents=False)
        except Exception:
            pass

        schema = (
            TextField("step"),
            TextField("tip"),
            VectorField("embedding", "FLAT", {
                "TYPE": "FLOAT32",
                "DIM": EMBEDDING_DIM,
                "DISTANCE_METRIC": "COSINE",
            }),
        )
        r.ft(INDEX_NAME).create_index(
            schema,
            definition=IndexDefinition(prefix=["mistake:"], index_type=IndexType.HASH),
        )

        for m in MISTAKES:
            vec = np.array(_embed(m["tip"]), dtype=np.float32).tobytes()
            r.hset(f"mistake:{m['id']}", mapping={
                "step": m["step"],
                "tip": m["tip"],
                "embedding": vec,
            })

        global _vector_ready
        _vector_ready = True
        print(f"[knowledge] Indexed {len(MISTAKES)} mistakes in Redis")
    except Exception as e:
        print(f"[knowledge] Vector index build failed ({e}) — using keyword fallback")


def lookup_tip(step_id: str) -> str:
    """Return the most relevant tip for a failed step."""
    if _vector_ready:
        return _vector_lookup(step_id)
    return _keyword_lookup(step_id)


def _keyword_lookup(step_id: str) -> str:
    matches = [m for m in MISTAKES if m["step"] == step_id]
    return matches[0]["tip"] if matches else ""


def _vector_lookup(step_id: str) -> str:
    r = _get_redis()
    if not r:
        return _keyword_lookup(step_id)
    try:
        import numpy as np
        from redis.commands.search.query import Query

        query_vec = np.array(_embed(step_id), dtype=np.float32).tobytes()
        q = (
            Query("*=>[KNN 1 @embedding $vec AS score]")
            .sort_by("score")
            .return_fields("tip", "score")
            .dialect(2)
        )
        results = r.ft(INDEX_NAME).search(q, query_params={"vec": query_vec})
        if results.docs:
            return results.docs[0].tip
    except Exception as e:
        print(f"[knowledge] Vector search error ({e})")
    return _keyword_lookup(step_id)
