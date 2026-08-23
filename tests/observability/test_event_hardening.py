from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.observability.events import AgentEvent, EventStatus


def _event(**kwargs: object) -> AgentEvent:
    values: dict[str, object] = {
        "occurred_at": datetime.now(timezone.utc),
        "request_id": "req-1",
        "component": "model",
        "event_type": "model.decision",
        "status": EventStatus.INFO,
        "message": "Model returned a decision.",
    }
    values.update(kwargs)
    return AgentEvent(**values)


@pytest.mark.parametrize(
    "metadata",
    (
        {"password": "secret"},
        {"nested": {"token": "secret"}},
        {"auth": {"api_key": "secret"}},
        {"headers": {"Authorization": "Bearer secret"}},
        {"private_key": "secret"},
    ),
)
def test_event_metadata_rejects_secret_shaped_keys(
    metadata: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        _event(metadata=metadata)


def test_event_metadata_allows_safe_filterable_values() -> None:
    event = _event(
        metadata={
            "attempt": 2,
            "budget": {
                "remaining_actions": 3,
            },
        }
    )

    payload = event.to_dict()

    assert payload["metadata"] == {
        "attempt": 2,
        "budget": {
            "remaining_actions": 3,
        },
    }
