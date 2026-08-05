from __future__ import annotations

import time

from src.pipeline.evidence_cache import EvidenceCache
from src.pipeline.evidence_package import EvidencePackage
from src.tool.capability_result import CapabilityStatus


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


def test_only_valid_evidence_statuses_are_cached() -> None:
    cache = EvidenceCache()
    valid = EvidencePackage(
        capability_name="CPU",
        evidence_name="CPU",
        data={"cores": 4},
        status=CapabilityStatus.VALID,
    )
    valid_empty = EvidencePackage(
        capability_name="Ports",
        evidence_name="Ports",
        data=[],
        status=CapabilityStatus.VALID_EMPTY,
    )

    assert cache.put("localhost", "CPU", valid) is True
    assert cache.put("localhost", "Ports", valid_empty) is True
    assert cache.get("localhost", "CPU") is valid
    assert cache.get("localhost", "Ports") is valid_empty


def test_failed_evidence_is_not_cached_as_a_hit() -> None:
    cache = EvidenceCache()
    failed = EvidencePackage(
        capability_name="CPU",
        evidence_name="CPU",
        status=CapabilityStatus.COLLECTION_FAILED,
        success=False,
        error="timeout",
    )

    assert cache.put("localhost", "CPU", failed) is False
    assert cache.get("localhost", "CPU") is None
    assert len(cache) == 0


def test_partial_evidence_is_not_cached_without_explicit_policy() -> None:
    cache = EvidenceCache()
    partial = EvidencePackage(
        capability_name="Network",
        evidence_name="Network",
        data={"interfaces": [{"name": "eth0"}]},
        status=CapabilityStatus.PARTIAL,
        success=False,
        error="route collection failed",
    )

    assert cache.put("localhost", "Network", partial) is False
    assert cache.get("localhost", "Network") is None


def test_invalid_write_does_not_replace_previous_valid_evidence() -> None:
    cache = EvidenceCache()
    valid = EvidencePackage(
        capability_name="CPU",
        evidence_name="CPU",
        data={"cores": 4},
    )
    failed = EvidencePackage(
        capability_name="CPU",
        evidence_name="CPU",
        status=CapabilityStatus.COLLECTION_FAILED,
        success=False,
        error="temporary failure",
    )

    assert cache.put("localhost", "CPU", valid) is True
    assert cache.put("localhost", "CPU", failed) is False
    assert cache.get("localhost", "CPU") is valid
