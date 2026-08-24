"""Canonical structured events for Orion runtime activity."""

from __future__ import annotations

import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType


class EventStatus(str, Enum):
    INFO = "info"
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"


_FORBIDDEN_METADATA_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "bearer",
        "cmd",
        "command",
        "cookie",
        "credential",
        "credentials",
        "password",
        "private_key",
        "proxy_authorization",
        "secret",
        "set_cookie",
        "shell",
        "token",
    }
)

_MAX_METADATA_DEPTH = 16
_MAX_METADATA_ITEMS = 2048
_MAX_METADATA_TEXT_CHARS = 1024
_MAX_RETAINED_EVENTS = 4096


def _normalize_key(value: str) -> str:
    return value.strip().casefold().replace("-", "_").replace(" ", "_")


def _safe_metadata(
    value: object,
    *,
    depth: int = 0,
) -> object:
    if depth > _MAX_METADATA_DEPTH:
        raise ValueError(
            "Event metadata exceeds maximum nesting depth."
        )

    if value is None or isinstance(value, (int, float, bool)):
        return value

    if isinstance(value, str):
        if len(value) > _MAX_METADATA_TEXT_CHARS:
            raise ValueError("Event metadata text exceeds maximum length.")
        return value

    if isinstance(value, Mapping):
        if len(value) > _MAX_METADATA_ITEMS:
            raise ValueError(
                "Event metadata exceeds maximum item count."
            )

        result: dict[str, object] = {}

        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise ValueError(
                    "Event metadata keys must be non-empty strings."
                )

            normalized_key = _normalize_key(key)
            if (
                normalized_key in _FORBIDDEN_METADATA_KEYS
                or any(
                    sensitive in normalized_key
                    for sensitive in (
                        "api_key",
                        "authorization",
                        "credential",
                        "password",
                        "private_key",
                        "secret",
                        "token",
                    )
                )
            ):
                raise ValueError(
                    f"Event metadata contains forbidden key: {key!r}."
                )

            result[key] = _safe_metadata(
                item,
                depth=depth + 1,
            )

        return MappingProxyType(result)

    if isinstance(value, (list, tuple)):
        if len(value) > _MAX_METADATA_ITEMS:
            raise ValueError(
                "Event metadata exceeds maximum item count."
            )

        return tuple(
            _safe_metadata(item, depth=depth + 1)
            for item in value
        )

    raise ValueError(
        "Event metadata must contain JSON-safe values only."
    )


def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            key: _thaw(item)
            for key, item in value.items()
        }

    if isinstance(value, tuple):
        return [_thaw(item) for item in value]

    return value


@dataclass(frozen=True, slots=True)
class AgentEvent:
    occurred_at: datetime
    request_id: str
    component: str
    event_type: str
    status: EventStatus
    message: str | None = None

    chat_id: str | None = None
    project_id: str | None = None
    model: str | None = None
    tool: str | None = None
    capability_id: str | None = None
    target_ref: str | None = None
    source_ref: str | None = None
    duration_ms: float | None = None
    error_code: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.occurred_at, datetime)
            or self.occurred_at.tzinfo is None
            or self.occurred_at.utcoffset() is None
        ):
            raise ValueError(
                "occurred_at must be timezone-aware."
            )

        for field_name in (
            "request_id",
            "component",
            "event_type",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(
                    f"{field_name} must be a non-empty string."
                )

        if self.message is not None and (
            not isinstance(self.message, str)
            or not self.message
        ):
            raise ValueError(
                "message must be a non-empty string or None."
            )

        if not isinstance(self.status, EventStatus):
            raise ValueError(
                "status must be EventStatus."
            )

        if self.duration_ms is not None and (
            not isinstance(self.duration_ms, (int, float))
            or isinstance(self.duration_ms, bool)
            or self.duration_ms < 0
        ):
            raise ValueError(
                "duration_ms must be non-negative or None."
            )

        if not isinstance(self.metadata, Mapping):
            raise ValueError(
                "metadata must be an object."
            )

        object.__setattr__(
            self,
            "metadata",
            _safe_metadata(self.metadata),
        )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "occurred_at": self.occurred_at.isoformat(),
            "request_id": self.request_id,
            "component": self.component,
            "event_type": self.event_type,
            "status": self.status.value,
        }

        if self.message is not None:
            payload["message"] = self.message

        optional = {
            "chat_id": self.chat_id,
            "project_id": self.project_id,
            "model": self.model,
            "tool": self.tool,
            "capability_id": self.capability_id,
            "target_ref": self.target_ref,
            "source_ref": self.source_ref,
            "duration_ms": self.duration_ms,
            "error_code": self.error_code,
        }

        for key, value in optional.items():
            if value is not None:
                payload[key] = value

        payload["metadata"] = _thaw(self.metadata)

        return payload


class AgentEventStore:
    """Bounded in-process event stream and its derived public counters.

    The store deliberately accepts completed event objects only.  It never
    reconstructs events from trace summary counters, so UI/log projections and
    metrics share one production source of truth.
    """

    def __init__(self, *, max_events: int = _MAX_RETAINED_EVENTS) -> None:
        if type(max_events) is not int or max_events < 1:
            raise ValueError("max_events must be a positive integer.")
        self._max_events = max_events
        self._events: list[AgentEvent] = []
        self._lock = threading.RLock()

    def emit(self, event: AgentEvent) -> None:
        if not isinstance(event, AgentEvent):
            raise TypeError("event must be an AgentEvent.")
        with self._lock:
            self._events.append(event)
            del self._events[:-self._max_events]

    def events(self, *, request_id: str | None = None) -> tuple[AgentEvent, ...]:
        with self._lock:
            if request_id is None:
                return tuple(self._events)
            return tuple(event for event in self._events if event.request_id == request_id)

    def clear(self) -> None:
        """Test/support reset; normal production code only appends events."""
        with self._lock:
            self._events.clear()

    def metrics_snapshot(self) -> dict[str, int]:
        """Project operational counters from actual retained structured events."""
        counters = {
            "requests_completed": 0,
            "requests_failed": 0,
            "model_calls": 0,
            "discoveries": 0,
            "actions_proposed": 0,
            "action_rejections": 0,
            "execution_dispatches": 0,
            "successful_tool_results": 0,
            "successful_evidence": 0,
            "failed_tool_executions": 0,
            "failed_evidence": 0,
        }
        with self._lock:
            events = tuple(self._events)
        for event in events:
            if event.event_type == "request.completed":
                counters["requests_completed"] += 1
            elif event.event_type == "request.failed":
                counters["requests_failed"] += 1
            elif event.event_type == "model.started":
                counters["model_calls"] += 1
            elif event.event_type == "discovery.started":
                counters["discoveries"] += 1
            elif event.event_type == "action.proposed":
                counters["actions_proposed"] += 1
            elif event.event_type == "action.rejected":
                counters["action_rejections"] += 1
            elif event.event_type == "tool.started":
                counters["execution_dispatches"] += 1
            elif event.event_type == "tool.completed" and event.status is EventStatus.SUCCEEDED:
                counters["successful_tool_results"] += 1
            elif event.event_type == "tool.failed":
                counters["failed_tool_executions"] += 1
            elif event.event_type == "evidence.created":
                if event.status is EventStatus.SUCCEEDED:
                    counters["successful_evidence"] += 1
                else:
                    counters["failed_evidence"] += 1
        return counters


_event_store = AgentEventStore()


def get_event_store() -> AgentEventStore:
    """Return the shared production event stream."""
    return _event_store
