from __future__ import annotations

import time

from src.pipeline.evidence_cache import EvidenceCache


def test_put_and_get() -> None:
    cache = EvidenceCache(ttl=60)
    cache.put("localhost", "cpu", {"usage": 50})
    assert cache.get("localhost", "cpu") == {"usage": 50}


def test_get_expired() -> None:
    cache = EvidenceCache(ttl=0.01)
    cache.put("localhost", "mem", {"free": 100})
    time.sleep(0.02)
    assert cache.get("localhost", "mem") is None


def test_get_missing() -> None:
    cache = EvidenceCache()
    assert cache.get("localhost", "nonexistent") is None


def test_clear() -> None:
    cache = EvidenceCache()
    cache.put("localhost", "a", 1)
    cache.put("monitor", "b", 2)
    assert len(cache) == 2
    cache.clear()
    assert len(cache) == 0


def test_prune_expired() -> None:
    cache = EvidenceCache(ttl=0.01)
    cache.put("localhost", "fresh", "data")
    time.sleep(0.02)
    cache.put("localhost", "also_fresh", "data2")
    removed = cache.prune_expired()
    assert removed == 1  # "fresh" should be expired
    assert cache.get("localhost", "fresh") is None
    assert cache.get("localhost", "also_fresh") == "data2"


def test_overwrite() -> None:
    cache = EvidenceCache(ttl=60)
    cache.put("localhost", "key", "old")
    cache.put("localhost", "key", "new")
    assert cache.get("localhost", "key") == "new"


def test_different_types() -> None:
    cache = EvidenceCache()
    cache.put("localhost", "int", 42)
    cache.put("localhost", "string", "hello")
    cache.put("localhost", "dict", {"a": 1})
    assert cache.get("localhost", "int") == 42
    assert cache.get("localhost", "string") == "hello"
    assert cache.get("localhost", "dict") == {"a": 1}


def test_different_targets() -> None:
    """B3: Evidence for different targets should not collide."""
    cache = EvidenceCache(ttl=60)
    cache.put("localhost", "cpu", {"usage": 10})
    cache.put("monitor", "cpu", {"usage": 90})
    assert cache.get("localhost", "cpu") == {"usage": 10}
    assert cache.get("monitor", "cpu") == {"usage": 90}


def test_ttl_property() -> None:
    cache = EvidenceCache(ttl=30)
    assert cache.ttl == 30
