from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from src.shared.execution.command_result import redact_sensitive

if TYPE_CHECKING:
    from src.pipeline.fact import Fact


_SAFE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
_SENSITIVE_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "key",
    "password",
    "secret",
    "token",
}


def _utc(value: datetime | int | float | str | None) -> datetime:
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


def _safe_reference(value: str | None) -> str | None:
    if not value:
        return None
    redacted = redact_sensitive(value.strip())
    try:
        parts = urlsplit(redacted)
    except ValueError:
        return redacted[:500]
    query = urlencode(
        [
            (key, "<redacted>" if key.casefold() in _SENSITIVE_QUERY_KEYS else item)
            for key, item in parse_qsl(parts.query, keep_blank_values=True)
        ]
    )
    if not parts.netloc:
        return urlunsplit((parts.scheme, "", parts.path, query, ""))[:500]
    try:
        port = f":{parts.port}" if parts.port is not None else ""
    except ValueError:
        port = ""
    host = parts.hostname or ""
    return urlunsplit((parts.scheme, f"{host}{port}", parts.path, query, ""))[:500]


def _identifier(*parts: object) -> str:
    material = "\x1f".join(str(part) for part in parts)
    return f"src:{hashlib.sha256(material.encode('utf-8')).hexdigest()[:20]}"


def _safe_parameter(key: str, value: object) -> object:
    if key.casefold() in _SENSITIVE_QUERY_KEYS:
        return "<redacted>"
    if isinstance(value, Mapping):
        return tuple(
            sorted(
                (str(nested_key), _safe_parameter(str(nested_key), nested_value))
                for nested_key, nested_value in value.items()
            )
        )
    if isinstance(value, (set, frozenset)):
        return tuple(sorted((_safe_parameter("", item) for item in value), key=repr))
    if isinstance(value, (list, tuple)):
        return tuple(_safe_parameter("", item) for item in value)
    if isinstance(value, datetime):
        return _utc(value).isoformat()
    if isinstance(value, Enum):
        return _safe_parameter("", value.value)
    if isinstance(value, str):
        return redact_sensitive(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return _safe_parameter("", to_dict())
    return redact_sensitive(str(value))


def _serialize_parameter(value: object) -> object:
    if isinstance(value, tuple):
        if all(
            isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str)
            for item in value
        ):
            return {item[0]: _serialize_parameter(item[1]) for item in value}
        return [_serialize_parameter(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class Provenance:
    """Safe, serializable origin of one canonical fact."""

    source: str
    capability: str
    target: str
    observed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source_reference: str | None = None
    command_ids: tuple[str, ...] = ()
    parameters: tuple[tuple[str, object], ...] = ()
    schema_version: str = "1"
    id: str = field(default="")

    def __post_init__(self) -> None:
        observed = _utc(self.observed_at)
        object.__setattr__(self, "observed_at", observed)
        object.__setattr__(self, "source", redact_sensitive(self.source)[:80])
        object.__setattr__(self, "capability", redact_sensitive(self.capability)[:160])
        object.__setattr__(self, "target", redact_sensitive(self.target)[:160])
        object.__setattr__(
            self, "source_reference", _safe_reference(self.source_reference)
        )
        command_ids = tuple(
            command_id
            for command_id in self.command_ids
            if isinstance(command_id, str) and _SAFE_ID.fullmatch(command_id)
        )
        object.__setattr__(self, "command_ids", command_ids)
        params = tuple(
            sorted(
                (str(key), _safe_parameter(str(key), value))
                for key, value in self.parameters
            )
        )
        object.__setattr__(self, "parameters", params)
        identity = self.id or _identifier(
            self.source,
            self.capability,
            self.target,
            observed.isoformat(),
            self.source_reference,
            command_ids,
            params,
            self.schema_version,
        )
        if not _SAFE_ID.fullmatch(identity):
            raise ValueError("provenance id must be a safe opaque identifier")
        object.__setattr__(self, "id", identity)

    @property
    def parameter_map(self) -> dict[str, object]:
        return dict(self.parameters)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "capability": self.capability,
            "target": self.target,
            "observed_at": self.observed_at.isoformat(),
            "source_reference": self.source_reference,
            "command_ids": list(self.command_ids),
            "parameters": {
                key: _serialize_parameter(value) for key, value in self.parameters
            },
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class ClaimSourceLink:
    provenance_id: str
    label: str
    href: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "provenance_id": self.provenance_id,
            "label": self.label,
            "href": self.href,
        }


def claim_source_links(
    facts: tuple[Fact, ...] | list[Fact],
    *,
    base_urls: dict[str, str] | None = None,
) -> tuple[ClaimSourceLink, ...]:
    """Create deterministic, deduplicated claim links from fact provenance."""

    bases = {
        key.casefold(): value.rstrip("/") for key, value in (base_urls or {}).items()
    }
    links: dict[str, ClaimSourceLink] = {}
    for fact in facts:
        provenance = fact.provenance
        reference = provenance.source_reference
        href: str | None = None
        if reference:
            if reference.startswith(("https://", "http://")):
                href = _safe_reference(reference)
            elif reference.startswith("/") and provenance.source.casefold() in bases:
                href = _safe_reference(
                    f"{bases[provenance.source.casefold()]}{reference}"
                )
        links.setdefault(
            provenance.id,
            ClaimSourceLink(
                provenance_id=provenance.id,
                label=f"{provenance.source}:{provenance.capability}",
                href=href,
            ),
        )
    return tuple(links[key] for key in sorted(links))
