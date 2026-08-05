from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any

from src.pipeline.provenance import Provenance


class FactValidity(str, Enum):
    VALID = "valid"
    VALID_EMPTY = "valid_empty"
    COMMAND_FAILED = "command_failed"
    NOT_COLLECTED = "not_collected"
    UNSUPPORTED = "unsupported"
    STALE = "stale"
    SCHEMA_INVALID = "schema_invalid"
    CONTRADICTORY = "contradictory"


class FactFreshness(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"


_SAFE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,200}$")
_METRIC = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+$")


def utc_datetime(value: datetime | int | float | str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return (
            value.replace(tzinfo=timezone.utc)
            if value.tzinfo is None
            else value.astimezone(timezone.utc)
        )
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    except ValueError:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (
        parsed.replace(tzinfo=timezone.utc)
        if parsed.tzinfo is None
        else parsed.astimezone(timezone.utc)
    )


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType(
            {str(key): _freeze(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    return value


def thaw(value: Any) -> Any:
    if isinstance(value, (dict, MappingProxyType)):
        return {str(key): thaw(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, frozenset)):
        return [thaw(item) for item in value]
    if isinstance(value, datetime):
        return utc_datetime(value).isoformat()
    if isinstance(value, Enum):
        return thaw(value.value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    return str(value)


def _fact_id(
    metric: str,
    subject: str,
    target: str,
    observed_at: datetime,
    provenance_id: str,
    value: object,
) -> str:
    stable_value = json.dumps(
        thaw(value), sort_keys=True, default=str, separators=(",", ":")
    )
    material = "\x1f".join(
        (metric, subject, target, observed_at.isoformat(), provenance_id, stable_value)
    )
    return f"fact:{hashlib.sha256(material.encode('utf-8')).hexdigest()[:24]}"


@dataclass(frozen=True, slots=True)
class Fact:
    """Immutable canonical observation used by deterministic reasoning."""

    subject: str
    metric: str
    value: Any
    unit: str
    observed_at: datetime
    collected_at: datetime
    source: str
    target: str
    validity: FactValidity
    freshness: FactFreshness
    confidence: float
    provenance: Provenance
    id: str = field(default="")
    dimensions: Mapping[str, Any] = field(
        default_factory=lambda: MappingProxyType({}), repr=False
    )

    def __post_init__(self) -> None:
        observed = utc_datetime(self.observed_at)
        collected = utc_datetime(self.collected_at)
        object.__setattr__(self, "observed_at", observed)
        object.__setattr__(self, "collected_at", collected)
        if not isinstance(self.validity, FactValidity):
            object.__setattr__(self, "validity", FactValidity(str(self.validity)))
        if not isinstance(self.freshness, FactFreshness):
            object.__setattr__(self, "freshness", FactFreshness(str(self.freshness)))
        if not self.subject.strip():
            raise ValueError("fact subject is required")
        if not _METRIC.fullmatch(self.metric):
            raise ValueError("fact metric must be a canonical dotted identifier")
        if not self.target.strip() or not self.source.strip():
            raise ValueError("fact source and target are required")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("fact confidence must be between 0.0 and 1.0")
        object.__setattr__(self, "confidence", float(self.confidence))
        if self.validity is FactValidity.VALID:
            if not self.unit.strip():
                raise ValueError("VALID fact requires an explicit canonical unit")
            if self.value is None:
                raise ValueError("VALID fact requires an observed value")
        if self.value == 0 and self.validity is not FactValidity.VALID:
            raise ValueError("zero is only an observation when validity is VALID")
        frozen_value = _freeze(self.value)
        object.__setattr__(self, "value", frozen_value)
        dimensions = (
            self.dimensions
            if isinstance(self.dimensions, MappingProxyType)
            else MappingProxyType(dict(self.dimensions))
        )
        object.__setattr__(
            self,
            "dimensions",
            MappingProxyType(
                {str(key): _freeze(item) for key, item in dimensions.items()}
            ),
        )
        identity = self.id or _fact_id(
            self.metric,
            self.subject,
            self.target,
            observed,
            self.provenance.id,
            frozen_value,
        )
        if not _SAFE_ID.fullmatch(identity):
            raise ValueError("fact id must be a safe opaque identifier")
        object.__setattr__(self, "id", identity)

    @property
    def usable(self) -> bool:
        return self.validity in {FactValidity.VALID, FactValidity.VALID_EMPTY} and (
            self.freshness is not FactFreshness.STALE
        )

    def age_seconds(self, now: datetime | int | float | str | None = None) -> float:
        return max((utc_datetime(now) - self.collected_at).total_seconds(), 0.0)

    def as_stale(self) -> Fact:
        dimensions = dict(self.dimensions)
        value = self.value
        if value == 0:
            dimensions["observed_value"] = value
            value = None
        return replace(
            self,
            value=value,
            validity=FactValidity.STALE,
            freshness=FactFreshness.STALE,
            dimensions=dimensions,
        )

    def as_contradictory(self) -> Fact:
        dimensions = dict(self.dimensions)
        value = self.value
        if value == 0:
            dimensions["observed_value"] = value
            value = None
        return replace(
            self,
            value=value,
            validity=FactValidity.CONTRADICTORY,
            dimensions=dimensions,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "subject": self.subject,
            "metric": self.metric,
            "value": thaw(self.value),
            "unit": self.unit,
            "observed_at": self.observed_at.isoformat(),
            "collected_at": self.collected_at.isoformat(),
            "source": self.source,
            "target": self.target,
            "validity": self.validity.value,
            "freshness": self.freshness.value,
            "confidence": self.confidence,
            "provenance": self.provenance.to_dict(),
            "dimensions": thaw(self.dimensions),
        }
