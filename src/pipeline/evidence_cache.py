from __future__ import annotations

import time as _time
from dataclasses import dataclass


@dataclass(frozen=True)
class CacheKey:
    """Composite cache key: target + evidence name.

    Ensures evidence from different targets don't collide,
    and identical evidence requests across turns are reused.
    """

    target: str
    evidence_name: str


class EvidenceCache:
    """Per-session evidence cache with TTL expiration.

    Reuses collected evidence across turns within a session
    to avoid re-collecting the same data. Evidence expires
    after a configurable TTL (default 60s).

    Thread-safe — uses a simple dict with no locking needed
    for single-threaded agent usage.
    """

    def __init__(self, ttl: float = 60.0) -> None:
        """Initialize the evidence cache.

        Args:
            ttl: Time-to-live in seconds. Evidence older than this
                 is considered stale and will be re-collected.
        """
        self._ttl = ttl
        self._cache: dict[CacheKey, tuple[float, object]] = {}

    def get(self, target: str, evidence_name: str) -> object | None:
        """Retrieve cached evidence for a specific target if still fresh.

        Args:
            target: The investigation target (e.g., 'localhost').
            evidence_name: The evidence name (e.g., 'CPU', 'Memory').

        Returns:
            Cached evidence package if fresh, None otherwise.
        """
        key = CacheKey(target=target, evidence_name=evidence_name)
        entry = self._cache.get(key)
        if entry is None:
            return None
        timestamp, data = entry
        if _time.monotonic() - timestamp > self._ttl:
            del self._cache[key]
            return None
        return data

    def put(self, target: str, evidence_name: str, data: object) -> None:
        """Store evidence in the cache.

        Args:
            target: The investigation target.
            evidence_name: The evidence name.
            data: The evidence package to cache.
        """
        key = CacheKey(target=target, evidence_name=evidence_name)
        self._cache[key] = (_time.monotonic(), data)

    def clear(self) -> None:
        """Remove all cached entries."""
        self._cache.clear()

    def __len__(self) -> int:
        """Number of cached entries (including expired ones until accessed)."""
        return len(self._cache)

    def prune_expired(self) -> int:
        """Remove all expired entries. Returns count of removed items."""
        now = _time.monotonic()
        expired = [k for k, (ts, _) in self._cache.items() if now - ts > self._ttl]
        for k in expired:
            del self._cache[k]
        return len(expired)

    @property
    def ttl(self) -> float:
        """Time-to-live in seconds."""
        return self._ttl
