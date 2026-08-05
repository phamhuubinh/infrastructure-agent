from __future__ import annotations

import time
from datetime import datetime, timezone

from src.pipeline.evidence_cache import CacheKey, EvidenceCache
from src.pipeline.evidence_package import EvidencePackage
from src.pipeline.fact import Fact, FactFreshness, FactValidity
from src.pipeline.provenance import Provenance

NOW = datetime.now(timezone.utc)


def _package(metric: str = "cpu.usage") -> EvidencePackage:
    provenance = Provenance("linux", "get_cpu_usage", "server-1", NOW)
    fact = Fact(
        "system",
        metric,
        42,
        "percent",
        NOW,
        NOW,
        "linux",
        "server-1",
        FactValidity.VALID,
        FactFreshness.FRESH,
        1.0,
        provenance,
    )
    return EvidencePackage(
        "CPU Information",
        "CPU",
        data={"usage_percent": 42},
        facts=(fact,),
    )


def test_cache_key_includes_capability_params_timeframe_and_schema() -> None:
    base = CacheKey.build(
        target="server-1",
        capability="Service Status",
        params={"name": "nginx"},
        timeframe={"start": 1, "end": 2},
        schema_version="1",
    )

    assert base != CacheKey.build(
        target="server-1",
        capability="Service Status",
        params={"name": "docker"},
        timeframe={"start": 1, "end": 2},
        schema_version="1",
    )
    assert base != CacheKey.build(
        target="server-1",
        capability="Service Status",
        params={"name": "nginx"},
        timeframe={"start": 1, "end": 3},
        schema_version="1",
    )


def test_cache_does_not_cross_contaminate_parameters_or_timeframe() -> None:
    cache = EvidenceCache()
    package = _package()
    cache.put(
        "server-1",
        "Service Status",
        package,
        capability="Service Status",
        params={"name": "nginx"},
        timeframe={"start": 1, "end": 2},
    )

    assert (
        cache.get(
            "server-1",
            "Service Status",
            capability="Service Status",
            params={"name": "nginx"},
            timeframe={"start": 1, "end": 2},
        )
        is package
    )
    assert (
        cache.get(
            "server-1",
            "Service Status",
            capability="Service Status",
            params={"name": "docker"},
            timeframe={"start": 1, "end": 2},
        )
        is None
    )


def test_stale_hit_is_opt_in_marked_and_keeps_provenance() -> None:
    cache = EvidenceCache(ttl=0.01)
    package = _package()
    cache.put("server-1", "CPU", package, capability="CPU Information")
    time.sleep(0.02)

    stale = cache.get(
        "server-1",
        "CPU",
        capability="CPU Information",
        allow_stale=True,
    )

    assert isinstance(stale, EvidencePackage)
    assert stale.stale is True
    assert stale.facts[0].validity is FactValidity.STALE
    assert stale.facts[0].provenance == package.facts[0].provenance


def test_identity_ttl_is_longer_than_snapshot_ttl() -> None:
    cache = EvidenceCache(ttl=60)
    assert cache.ttl_policy["identity"] > cache.ttl_policy["snapshot"]
