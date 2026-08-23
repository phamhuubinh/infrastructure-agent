from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.observability.events import AgentEvent, EventStatus


def test_event_contains_filterable_agent_fields() -> None:
    event = AgentEvent(
        occurred_at=datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc),
        request_id="req-123",
        chat_id="chat-1",
        project_id="project-orion",
        component="tool_runtime",
        event_type="tool.completed",
        status=EventStatus.SUCCEEDED,
        tool="grafana",
        capability_id="grafana.metrics",
        target_ref="monitor",
        source_ref="grafana-prod",
        duration_ms=125.4,
        metadata={"fact_count": 7},
    )

    payload = event.to_dict()

    assert payload["request_id"] == "req-123"
    assert payload["component"] == "tool_runtime"
    assert payload["event_type"] == "tool.completed"
    assert payload["status"] == "succeeded"
    assert payload["tool"] == "grafana"
    assert payload["capability_id"] == "grafana.metrics"
    assert payload["metadata"] == {"fact_count": 7}


def test_event_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        AgentEvent(
            occurred_at=datetime(2026, 8, 23, 12, 0),
            request_id="req-123",
            component="model",
            event_type="model.started",
            status=EventStatus.STARTED,
        )
