from __future__ import annotations

import time

from src.pipeline.evidence_cache import EvidenceCache


def test_put_and_get() -> None:
    cache = EvidenceCache(ttl=60)
    cache.put("cpu", {"usage": 50})
    assert cache.get("cpu") == {"usage": 50}


def test_get_expired() -> None:
    cache = EvidenceCache(ttl=0.01)
    cache.put("mem", {"free": 100})
    time.sleep(0.02)
    assert cache.get("mem") is None


def test_get_missing() -> None:
    cache = EvidenceCache()
    assert cache.get("nonexistent") is None


def test_clear() -> None:
    cache = EvidenceCache()
    cache.put("a", 1)
    cache.put("b", 2)
    assert len(cache) == 2
    cache.clear()
    assert len(cache) == 0


def test_prune_expired() -> None:
    cache = EvidenceCache(ttl=0.01)
    cache.put("fresh", "data")
    time.sleep(0.02)
    cache.put("also_fresh", "data2")
    removed = cache.prune_expired()
    assert removed == 1  # "fresh" should be expired
    assert cache.get("fresh") is None
    assert cache.get("also_fresh") == "data2"


def test_overwrite() -> None:
    cache = EvidenceCache(ttl=60)
    cache.put("key", "old")
    cache.put("key", "new")
    assert cache.get("key") == "new"


def test_different_types() -> None:
    cache = EvidenceCache()
    cache.put("int", 42)
    cache.put("string", "hello")
    cache.put("dict", {"a": 1})
    assert cache.get("int") == 42
    assert cache.get("string") == "hello"
    assert cache.get("dict") == {"a": 1}
