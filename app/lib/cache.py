"""Tiny in-process TTL cache.

Used by the media adapters (weather, news, songs, social) so that every DJ
script generation does not fan out to upstream APIs.

Design notes:
  - dict + monotonic timestamps; no extra dependencies.
  - Thread-safe via a single lock — request volume is low (a few thousand req/min
    at most), so the contention cost is negligible compared to a real concurrent
    map and we get correctness for free.
  - LRU bound: when the dict exceeds ``max_entries``, the oldest insertion is
    evicted. Prevents unbounded growth on key explosions (e.g. one cache key per
    free-text query).
  - Swap to Redis later by reimplementing the same three methods (get, set,
    purge_expired) behind the same class name. Callers do not change.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Generic, Hashable, TypeVar

T = TypeVar("T")


class TTLCache(Generic[T]):
    """Per-key TTL cache with an LRU eviction bound.

    Each entry has its own ``ttl_seconds`` so different endpoints (weather 10m,
    news 15m, songs 7d, social 60s) can share one instance if desired — but in
    practice each adapter constructs its own.
    """

    def __init__(self, *, default_ttl: float, max_entries: int = 1024) -> None:
        if default_ttl <= 0:
            raise ValueError("default_ttl must be > 0")
        if max_entries <= 0:
            raise ValueError("max_entries must be > 0")
        self._default_ttl = float(default_ttl)
        self._max_entries = int(max_entries)
        self._store: OrderedDict[Hashable, tuple[float, T]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: Hashable) -> T | None:
        """Return the cached value for ``key`` or ``None`` if missing/expired."""
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at < now:
                # Expired — drop it.
                self._store.pop(key, None)
                return None
            # Touch for LRU ordering.
            self._store.move_to_end(key)
            return value

    def set(self, key: Hashable, value: T, *, ttl: float | None = None) -> None:
        """Insert ``value`` for ``key``. Overwrites any existing entry."""
        ttl_secs = float(ttl) if ttl is not None else self._default_ttl
        if ttl_secs <= 0:
            raise ValueError("ttl must be > 0")
        expires_at = time.monotonic() + ttl_secs
        with self._lock:
            self._store[key] = (expires_at, value)
            self._store.move_to_end(key)
            # Evict oldest entries if over the bound.
            while len(self._store) > self._max_entries:
                self._store.popitem(last=False)

    def purge_expired(self) -> int:
        """Drop every expired entry. Returns number removed. Mostly for tests."""
        now = time.monotonic()
        removed = 0
        with self._lock:
            for key in list(self._store.keys()):
                expires_at, _ = self._store[key]
                if expires_at < now:
                    self._store.pop(key, None)
                    removed += 1
        return removed

    def clear(self) -> None:
        """Drop everything. Used by tests."""
        with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)


def cache_key(*parts: Any) -> tuple[Any, ...]:
    """Build a stable cache key from arbitrary parts.

    Strings are lowercased and stripped so different casings of the same query
    share the same cache slot. ``None`` parts are included so the key still
    discriminates between presence and absence.
    """
    out: list[Any] = []
    for p in parts:
        if isinstance(p, str):
            out.append(p.strip().lower())
        else:
            out.append(p)
    return tuple(out)
