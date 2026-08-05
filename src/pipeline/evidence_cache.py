from __future__ import annotations

import threading
import time as _time
from dataclasses import dataclass

from src.pipeline.evidence_package import EvidencePackage


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

    Thread-safe so a session remains safe if multiple application threads
    inspect or clear its cache.
    """

    def __init__(self, ttl: float = 60.0) -> None:
        """Initialize the evidence cache.

        Args:
            ttl: Time-to-live in seconds. Evidence older than this
                 is considered stale and will be re-collected.
        """
        self._ttl = ttl
        self._cache: dict[CacheKey, tuple[float, object]] = {}
        self._lock = threading.RLock()

    def get(self, target: str, evidence_name: str) -> object | None:
        """Retrieve cached evidence for a specific target if still fresh.

        Args:
            target: The investigation target (e.g., 'localhost').
            evidence_name: The evidence name (e.g., 'CPU', 'Memory').

        Returns:
            Cached evidence package if fresh, None otherwise.
        """
        key = CacheKey(target=target, evidence_name=evidence_name)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            timestamp, data = entry
            if _time.monotonic() - timestamp > self._ttl:
                del self._cache[key]
                return None
            if isinstance(data, EvidencePackage) and not data.valid_for_requirements:
                # Defense in depth for entries created by older versions or
                # direct state restoration. Invalid evidence is never a hit.
                del self._cache[key]
                return None
            return data

    def put(self, target: str, evidence_name: str, data: object) -> bool:
        """Store cacheable data, rejecting failed or partial evidence.

        Args:
            target: The investigation target.
            evidence_name: The evidence name.
            data: The evidence package to cache.

        Returns:
            True when stored; False when evidence policy rejects the value.
        """
        if isinstance(data, EvidencePackage) and not data.valid_for_requirements:
            return False
        key = CacheKey(target=target, evidence_name=evidence_name)
        with self._lock:
            self._cache[key] = (_time.monotonic(), data)
        return True

    def clear(self) -> None:
        """Remove all cached entries."""
        with self._lock:
            self._cache.clear()

    def __len__(self) -> int:
        """Number of cached entries (including expired ones until accessed)."""
        with self._lock:
            return len(self._cache)

    def prune_expired(self) -> int:
        """Remove all expired entries. Returns count of removed items."""
        now = _time.monotonic()
        with self._lock:
            expired = [
                key
                for key, (timestamp, _) in self._cache.items()
                if now - timestamp > self._ttl
            ]
            for key in expired:
                del self._cache[key]
            return len(expired)

    @property
    def ttl(self) -> float:
        """Time-to-live in seconds."""
        return self._ttl
