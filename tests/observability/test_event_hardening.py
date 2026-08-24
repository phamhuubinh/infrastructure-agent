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


def test_event_accepts_complete_safe_provider_generation_diagnostics() -> None:
    event = _event(
        event_type="model.failed",
        status=EventStatus.FAILED,
        metadata={
            "parse_diagnostics": {
                "response_type": "str",
                "provider_generation": {
                    "finish_reason": "length",
                    "completion_count": 1024,
                    "prompt_count": 312,
                    "stop_sequence_configured": False,
                    "content_bytes_before_sanitization": 1309,
                    "content_bytes_after_sanitization": 1309,
                    "provider_http_status": 200,
                },
            }
        },
    )

    assert event.to_dict()["metadata"]["parse_diagnostics"]["provider_generation"] == {
        "finish_reason": "length",
        "completion_count": 1024,
        "prompt_count": 312,
        "stop_sequence_configured": False,
        "content_bytes_before_sanitization": 1309,
        "content_bytes_after_sanitization": 1309,
        "provider_http_status": 200,
    }
