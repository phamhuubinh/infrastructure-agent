from __future__ import annotations

import json
import threading
from types import SimpleNamespace
from unittest import mock

from src.backend.routers.query import _sanitize_execution_trace, query


def _request(deps: object) -> SimpleNamespace:
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(deps=deps)))


def test_query_preserves_contract_and_exposes_safe_planner_trace() -> None:
    agent = mock.MagicMock()
    agent.run_with_steps.return_value = {
        "steps": [{"tool": "fixture", "result": "ok"}],
        "response": "Server is healthy.",
        "trace_id": "trace-61",
        "execution_trace": {
            "trace_id": "trace-61",
            "user_request": "check cpu token=super-secret",
            "answer_strategy": "LLM_ASSESSMENT",
            "system_prompt": "do not expose this prompt",
            "runtime_metrics": {
                "semantic_loop": {
                    "planner": {
                        "status": "valid",
                        "provider": "fixture",
                        "model": "planner-test",
                        "estimated_input_tokens": 42,
                        "configured_effort": "minimal",
                        "system_prompt": "private planner prompt",
                        "hidden_reasoning": "private thoughts",
                    },
                    "validation": {
                        "status": "valid",
                        "reason": "valid",
                    },
                },
                "model_usage": {
                    "calls": 1,
                    "per_call": [
                        {
                            "purpose": "planner",
                            "input_tokens": 10,
                            "reasoning_tokens": 2,
                            "visible_output_tokens": 5,
                            "configured_effort": "minimal",
                            "api_key": "super-secret",
                        }
                    ],
                },
            },
        },
    }
    deps = SimpleNamespace(
        prepare_query=mock.MagicMock(
            return_value=("session-61", agent, threading.RLock())
        )
    )

    response = query(
        {
            "question": "check cpu",
            "session_id": "session-61",
            "asked_at": "2026-08-18T08:00:00+00:00",
        },
        _request(deps),
    )

    assert set(response) == {
        "session_id",
        "steps",
        "assessment",
        "response_time_ms",
        "asked_at",
        "trace_id",
        "execution_trace",
    }
    assert response["assessment"] == "Server is healthy."
    assert response["steps"] == [{"tool": "fixture", "result": "ok"}]
    assert response["trace_id"] == "trace-61"

    trace = response["execution_trace"]
    assert isinstance(trace, dict)
    assert trace["trace_id"] == "trace-61"
    assert trace["user_request"] == "check cpu token=<redacted>"

    semantic = trace["runtime_metrics"]["semantic_loop"]
    assert semantic["planner"]["provider"] == "fixture"
    assert semantic["planner"]["estimated_input_tokens"] == 42
    assert semantic["planner"]["configured_effort"] == "minimal"
    assert semantic["validation"] == {"status": "valid", "reason": "valid"}

    usage = trace["runtime_metrics"]["model_usage"]
    assert usage["per_call"][0]["reasoning_tokens"] == 2
    assert usage["per_call"][0]["configured_effort"] == "minimal"

    serialized = json.dumps(trace)
    assert "super-secret" not in serialized
    assert "private planner prompt" not in serialized
    assert "private thoughts" not in serialized
    assert "system_prompt" not in serialized
    assert "hidden_reasoning" not in serialized
    assert "api_key" not in serialized


def test_execution_trace_boundary_is_bounded_and_fails_closed() -> None:
    oversized = {
        "trace_id": "large-trace",
        "answer_strategy": "LLM_ASSESSMENT",
        "runtime_metrics": {
            "custom": ["x" * 10_000 for _ in range(100)],
        },
    }

    trace = _sanitize_execution_trace(oversized)

    assert trace is not None
    encoded = json.dumps(trace, ensure_ascii=False).encode("utf-8")
    assert len(encoded) <= 128 * 1024
    assert trace["trace_id"] == "large-trace"


def test_query_keeps_regeneration_transaction_and_trace_contract() -> None:
    agent = mock.MagicMock()
    snapshot = [{"role": "user", "content": "old"}]
    agent.conversation_store.truncate_for_regeneration.return_value = snapshot
    agent.run_with_steps.return_value = {
        "steps": [],
        "response": "regenerated",
        "trace_id": "regen-trace",
        "execution_trace": {"trace_id": "regen-trace"},
    }
    deps = SimpleNamespace(
        prepare_query=mock.MagicMock(
            return_value=("regen-session", agent, threading.RLock())
        )
    )

    response = query(
        {
            "question": "regenerate",
            "session_id": "regen-session",
            "regenerate_turn_index": 1,
        },
        _request(deps),
    )

    assert response["session_id"] == "regen-session"
    assert response["assessment"] == "regenerated"
    assert response["steps"] == []
    assert response["trace_id"] == "regen-trace"
    assert response["execution_trace"] == {"trace_id": "regen-trace"}
    agent.conversation_store.truncate_for_regeneration.assert_called_once_with(1)
    agent.conversation_store.restore_messages.assert_not_called()
