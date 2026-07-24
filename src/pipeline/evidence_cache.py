from __future__ import annotations

import time as _time
from collections.abc import Hashable


class EvidenceCache:
    """Per-session evidence cache with TTL expiration.

    Reuses collected evidence across turns within a session
    to avoid re-collecting the same data. Evidence expires
    after a configurable TTL.

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
        self._cache: dict[Hashable, tuple[float, object]] = {}

    def get(self, key: Hashable) -> object | None:
        """Retrieve cached evidence if still fresh.

        Args:
            key: The cache key (typically evidence_name or capability_name).

        Returns:
            Cached data if fresh, None otherwise.
        """
        entry = self._cache.get(key)
        if entry is None:
            return None
        timestamp, data = entry
        if _time.monotonic() - timestamp > self._ttl:
            del self._cache[key]
            return None
        return data

    def put(self, key: Hashable, data: object) -> None:
        """Store evidence in the cache.

        Args:
            key: The cache key.
            data: The evidence data to cache.
        """
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
