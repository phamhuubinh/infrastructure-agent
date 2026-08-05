from __future__ import annotations

import threading
import time as _time
from dataclasses import dataclass, replace
from types import MappingProxyType

from src.pipeline.evidence_package import EvidencePackage
from src.pipeline.fact import Fact
from src.pipeline.time_range_resolver import TimeRange


def _freeze(value: object) -> object:
    if isinstance(value, MappingProxyType):
        value = dict(value)
    if isinstance(value, dict):
        return tuple(sorted((str(key), _freeze(item)) for key, item in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return tuple(sorted((_freeze(item) for item in value), key=repr))
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return _freeze(to_dict())
    return value


def _params(value: object) -> tuple[tuple[str, object], ...]:
    if value is None:
        return ()
    if isinstance(value, dict):
        raw = list(value.items())
    elif isinstance(value, (tuple, list)):
        raw = [
            (item[0], item[1])
            for item in value
            if isinstance(item, (tuple, list)) and len(item) == 2
        ]
    else:
        to_dict = getattr(value, "to_dict", None)
        mapped = to_dict() if callable(to_dict) else {}
        raw = list(mapped.items()) if isinstance(mapped, dict) else []
    return tuple(sorted((str(key), _freeze(item)) for key, item in raw))


def _timeframe(value: object) -> object:
    if isinstance(value, TimeRange):
        return _freeze(value.to_dict())
    return _freeze(value)


@dataclass(frozen=True, slots=True)
class CacheKey:
    target: str
    capability: str
    normalized_params: tuple[tuple[str, object], ...] = ()
    timeframe: object = None
    schema_version: str = "1"

    @classmethod
    def build(
        cls,
        *,
        target: str,
        capability: str,
        params: object = None,
        timeframe: object = None,
        schema_version: str = "1",
    ) -> CacheKey:
        return cls(
            target=target.strip(),
            capability=capability.strip(),
            normalized_params=_params(params),
            timeframe=_timeframe(timeframe),
            schema_version=str(schema_version),
        )


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    stored_at: float
    ttl: float
    data: object


class EvidenceCache:
    """Thread-safe evidence cache keyed by the complete collection contract."""

    def __init__(
        self,
        ttl: float = 60.0,
        *,
        ttl_by_fact_class: dict[str, float] | None = None,
    ) -> None:
        self._ttl = ttl
        self._ttl_by_fact_class = {
            "identity": max(ttl, 3600.0),
            "event": max(ttl, 300.0),
            "snapshot": ttl,
            **(ttl_by_fact_class or {}),
        }
        self._cache: dict[CacheKey, _CacheEntry] = {}
        self._lock = threading.RLock()

    def get(
        self,
        target: str,
        evidence_name: str | None = None,
        *,
        capability: str | None = None,
        params: object = None,
        timeframe: object = None,
        schema_version: str = "1",
        allow_stale: bool = False,
    ) -> object | None:
        key = CacheKey.build(
            target=target,
            capability=capability or evidence_name or "",
            params=params,
            timeframe=timeframe,
            schema_version=schema_version,
        )
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            expired = _time.monotonic() - entry.stored_at > entry.ttl
            if expired:
                if allow_stale:
                    return self._mark_stale(entry.data)
                del self._cache[key]
                return None
            data = entry.data
            if isinstance(data, EvidencePackage) and not data.valid_for_requirements:
                del self._cache[key]
                return None
            return data

    def put(
        self,
        target: str,
        evidence_name: str | None,
        data: object,
        *,
        capability: str | None = None,
        params: object = None,
        timeframe: object = None,
        schema_version: str = "1",
    ) -> bool:
        if isinstance(data, EvidencePackage) and not data.valid_for_requirements:
            return False
        key = CacheKey.build(
            target=target,
            capability=capability or evidence_name or "",
            params=params,
            timeframe=timeframe,
            schema_version=schema_version,
        )
        entry = _CacheEntry(
            stored_at=_time.monotonic(),
            ttl=self._ttl_for(data),
            data=data,
        )
        with self._lock:
            self._cache[key] = entry
        return True

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)

    def prune_expired(self) -> int:
        now = _time.monotonic()
        with self._lock:
            expired = [
                key
                for key, entry in self._cache.items()
                if now - entry.stored_at > entry.ttl
            ]
            for key in expired:
                del self._cache[key]
            return len(expired)

    @property
    def ttl(self) -> float:
        return self._ttl

    @property
    def ttl_policy(self) -> dict[str, float]:
        return dict(self._ttl_by_fact_class)

    def _ttl_for(self, data: object) -> float:
        if not isinstance(data, EvidencePackage) or not data.facts:
            return self._ttl_by_fact_class["snapshot"]
        classes = {self._fact_class(fact) for fact in data.facts}
        return min(self._ttl_by_fact_class[item] for item in classes)

    @staticmethod
    def _fact_class(fact: Fact) -> str:
        if fact.metric.startswith("monitoring.") and fact.unit == "event":
            return "event"
        if fact.metric in {
            "system.hostname",
            "system.kernel",
            "system.os",
            "cpu.model",
            "cpu.logical_cores",
        }:
            return "identity"
        return "snapshot"

    @staticmethod
    def _mark_stale(data: object) -> object:
        if not isinstance(data, EvidencePackage):
            return data
        return replace(
            data,
            facts=tuple(fact.as_stale() for fact in data.facts),
            stale=True,
        )
