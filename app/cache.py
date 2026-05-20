"""
Redis-backed cache for tool results and embeddings.

Two primary use cases:

1. **Embedding cache (`cached_embed`)** — content-addressed, infinite TTL.
   Identical text never re-embedded. Expected hit rate 60-80% at steady state
   on a corpus with repeated findings (same news article, same registry record).

2. **Tool result cache (`cached_tool_call`)** — keyed by (tool name + canonical
   args hash), TTL configurable per tool. Saves 3rd-party API costs +
   round-trip latency for expensive enrichment tools.

Design choices:
- Single Redis instance, AOF every-second persistence, allkeys-lru eviction.
- All entries msgpack-encoded for compact storage. (Falls back to JSON if
  msgpack isn't installed — see _PACK.)
- Connection is lazy: first call dials in, subsequent calls reuse the pool.
- If Redis is down (REDIS_URL unset or connection refused), the cache is a
  transparent no-op — the wrapped function still runs, just without caching.
  This is intentional: caching must never be a hard dependency.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any, Callable

log = logging.getLogger(__name__)

# ── Pluggable codec — prefer msgpack for size, fall back to json. ─────────────
try:
    import msgpack
    def _pack(v: Any) -> bytes:   return msgpack.packb(v, use_bin_type=True)
    def _unpack(b: bytes) -> Any: return msgpack.unpackb(b, raw=False)
except ImportError:
    def _pack(v: Any) -> bytes:   return json.dumps(v, default=str).encode("utf-8")
    def _unpack(b: bytes) -> Any: return json.loads(b.decode("utf-8"))


# ── Lazy Redis client (None if disabled / unreachable). ───────────────────────
_redis = None
_redis_probed = False


def _get_redis():
    """Lazy-init Redis client. Returns None if disabled or unreachable."""
    global _redis, _redis_probed
    if _redis_probed:
        return _redis
    _redis_probed = True

    url = os.environ.get("REDIS_URL")
    if not url:
        log.info("Cache: REDIS_URL not set — caching disabled (no-op).")
        return None

    try:
        import redis  # type: ignore
        client = redis.Redis.from_url(url, socket_connect_timeout=2)
        client.ping()
        _redis = client
        log.info("Cache: connected to Redis at %s", url)
    except Exception as e:
        log.warning("Cache: Redis unreachable (%s) — caching disabled.", e)
        _redis = None
    return _redis


# ── Hashing helpers ───────────────────────────────────────────────────────────
def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_args_hash(args: dict[str, Any] | tuple | list) -> str:
    """
    Stable hash of tool-call args. Sorts dict keys so {a:1,b:2} == {b:2,a:1}.
    """
    canon = json.dumps(args, sort_keys=True, default=str, separators=(",", ":"))
    return _sha256(canon)


# ── Embedding cache ───────────────────────────────────────────────────────────
def cached_embed(text: str, embed_fn: Callable[[str], list[float]]) -> list[float]:
    """
    Wrap an embedding function with a content-hash cache.

    Empty/whitespace-only text is short-circuited to a zero vector at the
    caller layer (preserved behavior).
    """
    if not text:
        return embed_fn(text)

    r = _get_redis()
    if r is None:
        return embed_fn(text)

    key = f"embed:v1:{_sha256(text)}"
    try:
        hit = r.get(key)
        if hit:
            return _unpack(hit)
    except Exception as e:
        log.debug("Cache: embedding get failed (%s) — bypassing.", e)
        return embed_fn(text)

    vec = embed_fn(text)
    try:
        # No TTL — embeddings are content-addressed; identical text always
        # produces the same vector for a given model.
        r.set(key, _pack(vec))
    except Exception as e:
        log.debug("Cache: embedding set failed (%s).", e)
    return vec


# ── Tool-result cache ─────────────────────────────────────────────────────────
def cached_tool_call(
    tool_name: str,
    args: dict[str, Any] | tuple | list,
    fn: Callable[[], Any],
    ttl_seconds: int = 3600,
    *,
    cache_safe: bool = True,
) -> Any:
    """
    Wrap a tool call with a (tool, args) → result cache.

    Args:
        tool_name: short identifier — e.g. "run_news_search", "run_sec_lookup".
        args: canonicalized args. Order-independent for dicts.
        fn: zero-arg thunk that performs the real call. Only invoked on miss.
        ttl_seconds: cache lifetime. Tune per tool:
            news/web search → 3600 (1h)
            registry/SEC lookups → 604800 (7d)
            web crawls → 86400 (24h)
        cache_safe: opt-in flag. Set False to bypass cache entirely (e.g.
            queries containing per-user identifiers that mustn't cross users).

    Returns the result (cached or live). If anything in the cache path fails,
    falls through to a live call.
    """
    if not cache_safe:
        return fn()

    r = _get_redis()
    if r is None:
        return fn()

    key = f"tool:v1:{tool_name}:{_canonical_args_hash(args)}"
    try:
        hit = r.get(key)
        if hit:
            log.debug("Cache HIT %s", key)
            return _unpack(hit)
    except Exception as e:
        log.debug("Cache: tool get failed (%s) — bypassing.", e)
        return fn()

    result = fn()

    # Only cache successful results. Define "success" loosely: not None,
    # not an Exception. Callers may pass dict results with error keys; we still
    # cache those — the assumption is the caller decided this is the answer.
    if result is None or isinstance(result, Exception):
        return result

    try:
        r.setex(key, ttl_seconds, _pack(result))
    except Exception as e:
        log.debug("Cache: tool set failed (%s).", e)
    return result


# ── Async tool-call cache (for async node implementations) ───────────────────
async def cached_tool_call_async(
    tool_name: str,
    args: dict[str, Any] | tuple | list,
    async_fn,
    ttl_seconds: int = 3600,
    *,
    cache_safe: bool = True,
):
    """Async sibling of cached_tool_call. async_fn is an awaitable producing the result."""
    if not cache_safe:
        return await async_fn()

    r = _get_redis()
    if r is None:
        return await async_fn()

    key = f"tool:v1:{tool_name}:{_canonical_args_hash(args)}"
    try:
        hit = r.get(key)
        if hit:
            log.debug("Cache HIT %s", key)
            return _unpack(hit)
    except Exception as e:
        log.debug("Cache: async tool get failed (%s) — bypassing.", e)
        return await async_fn()

    result = await async_fn()
    if result is None or isinstance(result, Exception):
        return result

    try:
        r.setex(key, ttl_seconds, _pack(result))
    except Exception as e:
        log.debug("Cache: async tool set failed (%s).", e)
    return result


# ── Stats helper for observability ────────────────────────────────────────────
def cache_stats() -> dict[str, Any]:
    """Snapshot for the burn-in health check or admin dashboard."""
    r = _get_redis()
    if r is None:
        return {"enabled": False}
    try:
        info = r.info(section="stats")
        keyspace = r.info(section="keyspace")
        return {
            "enabled": True,
            "keyspace_hits": info.get("keyspace_hits", 0),
            "keyspace_misses": info.get("keyspace_misses", 0),
            "hit_rate": (
                info["keyspace_hits"]
                / max(1, info["keyspace_hits"] + info["keyspace_misses"])
                if "keyspace_hits" in info else None
            ),
            "db0": keyspace.get("db0", {}),
            "evicted_keys": info.get("evicted_keys", 0),
        }
    except Exception as e:
        return {"enabled": True, "error": str(e)}
