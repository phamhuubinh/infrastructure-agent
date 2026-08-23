from __future__ import annotations

import json
import threading
from types import SimpleNamespace
from unittest import mock

from src.agent.canonical_factory import (
    create_canonical_session_agent,
)
from src.agent.contracts import (
    AgentAction,
    AgentDecision,
    DecisionKind,
)
from src.backend.routers.query import (
    _sanitize_execution_trace,
    query,
)
from src.model.agent_backend import (
    AgentModelBackend,
)
from src.shared.config import OrionConfig
from src.shared.execution.tool_result import ToolResult
from src.tool.capability_result import CapabilityStatus


def _request(deps: object) -> SimpleNamespace:
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                deps=deps
            )
        )
    )


def _wire(
    kind: DecisionKind,
    *,
    answer: str | None = None,
    capability_id: str | None = None,
    target_ref: str | None = None,
) -> str:
    if kind is DecisionKind.FINAL:
        decision = AgentDecision(
            kind=DecisionKind.FINAL,
            goal="Answer the request.",
            answer=answer,
        )
    elif kind is DecisionKind.ACTION:
        if capability_id is None:
            raise ValueError(
                "action requires capability_id"
            )

        decision = AgentDecision(
            kind=DecisionKind.ACTION,
            goal="Follow the request.",
            action=AgentAction(
                capability_id=capability_id,
                target_ref=target_ref,
            ),
        )
    else:
        raise ValueError(
            f"unsupported test decision {kind}"
        )

    return json.dumps(
        decision.to_wire()
    )


class _QueuedAssessmentModel(
    AgentModelBackend
):
    def __init__(
        self,
        responses: list[str],
    ) -> None:
        self.responses = responses

    def assess(
        self,
        _request: object,
    ) -> str:
        raise AssertionError(
            "canonical agent must use "
            "structured agent-provider calls"
        )

    def complete(
        self,
        _prompt: str,
    ) -> str:
        return self.responses.pop(0)


def _config() -> OrionConfig:
    return OrionConfig(
        servers={},
        active_server_name="",
        tools={},
    )


def test_query_runs_canonical_final_through_public_contract(
    tmp_path,
) -> None:
    request_secret = (
        "REQUEST_SECRET_SENTINEL"
    )
    final_secret = (
        "FINAL_SECRET_SENTINEL"
    )

    agent = create_canonical_session_agent(
        target_store_path=str(
            tmp_path / "targets.json"
        ),
        model_backend=(
            _QueuedAssessmentModel(
                [
                    _wire(
                        DecisionKind.FINAL,
                        answer=(
                            "API final. "
                            f"token={final_secret}"
                        ),
                    )
                ]
            )
        ),
        config=_config(),
    )

    deps = SimpleNamespace(
        prepare_query=mock.MagicMock(
            return_value=(
                "session-canonical",
                agent,
                threading.RLock(),
            )
        )
    )

    response = query(
        {
            "question": (
                "Explain status "
                f"{request_secret}"
            ),
            "session_id": (
                "session-canonical"
            ),
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

    assert (
        response["session_id"]
        == "session-canonical"
    )
    assert (
        response["assessment"]
        == "API final. token=<redacted>"
    )
    assert response["steps"] == []
    assert isinstance(
        response["trace_id"],
        str,
    )

    trace = response[
        "execution_trace"
    ]

    assert trace is not None
    assert (
        trace["trace_id"]
        == response["trace_id"]
    )
    assert trace["user_request"] == ""

    runtime = trace[
        "runtime_metrics"
    ]["canonical_runtime"]

    assert runtime["terminal"] == "final"
    assert runtime["model_calls"] == 1
    assert runtime[
        "discovery_calls"
    ] == 0
    assert runtime[
        "action_attempts"
    ] == 0
    assert runtime[
        "observation_count"
    ] == 0
    assert runtime["failure"] is None
    assert runtime[
        "approval_required"
    ] is False

    assert runtime["budget"] == {
        "max_actions": 6,
        "actions_used": 0,
        "max_cost": 12,
        "cost_used": 0,
    }

    rendered = json.dumps(
        response
    )

    assert (
        request_secret
        not in rendered
    )
    assert (
        final_secret
        not in rendered
    )
    assert (
        "system_prompt"
        not in rendered
    )
    assert (
        "user_prompt"
        not in rendered
    )


def test_query_projects_canonical_action_steps_without_raw_evidence(
    tmp_path,
    monkeypatch,
) -> None:
    target_store = (
        tmp_path / "targets.json"
    )

    target_store.write_text(
        json.dumps(
            {
                "targets": {
                    "monitor": {
                        "backend": "local"
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    agent = create_canonical_session_agent(
        target_store_path=str(
            target_store
        ),
        model_backend=(
            _QueuedAssessmentModel(
                [
                    # Preliminary capability
                    # selection: not authority.
                    _wire(
                        DecisionKind.ACTION,
                        capability_id=(
                            "host.get_cpu"
                        ),
                    ),
                    # Detailed structured
                    # proposal: exact target.
                    _wire(
                        DecisionKind.ACTION,
                        capability_id=(
                            "host.get_cpu"
                        ),
                        target_ref="monitor",
                    ),
                    _wire(
                        DecisionKind.FINAL,
                        answer=(
                            "CPU observation for "
                            "monitor received."
                        ),
                    ),
                ]
            )
        ),
        config=_config(),
    )

    deps = SimpleNamespace(
        prepare_query=mock.MagicMock(
            return_value=(
                "session-action",
                agent,
                threading.RLock(),
            )
        )
    )

    raw_evidence = (
        "RAW_EVIDENCE_SENTINEL"
    )

    monkeypatch.setattr(
        "src.tool.linux_tool.LinuxTool.execute",
        (
            lambda _tool, _arguments:
            ToolResult(
                success=True,
                data={
                    "logical_cores": 4,
                    "raw_payload": (
                        raw_evidence
                    ),
                },
                capability_status=(
                    CapabilityStatus.VALID
                ),
            )
        ),
    )

    response = query(
        {
            "question": (
                "Inspect monitor."
            ),
            "session_id": (
                "session-action"
            ),
        },
        _request(deps),
    )

    assert len(
        response["steps"]
    ) == 1

    step = response[
        "steps"
    ][0]

    assert step["type"] == "evidence"
    assert (
        step["capability_id"]
        == "host.get_cpu"
    )
    assert step["status"] == "success"
    assert (
        step["target_id"]
        == "monitor"
    )
    assert (
        step["source_id"]
        == "monitor"
    )

    rendered = json.dumps(
        response
    )

    assert (
        raw_evidence
        not in rendered
    )
    assert (
        "logical_cores"
        not in json.dumps(step)
    )

    runtime = response[
        "execution_trace"
    ]["runtime_metrics"][
        "canonical_runtime"
    ]

    assert runtime[
        "action_attempts"
    ] == 1
    assert runtime[
        "observation_count"
    ] == 1
    assert runtime["budget"][
        "actions_used"
    ] == 1


def test_query_preserves_contract_and_sanitizes_canonical_trace() -> None:
    agent = mock.MagicMock()

    agent.run_with_steps.return_value = {
        "steps": [
            {
                "type": "evidence",
                "capability_id": (
                    "host.get_cpu"
                ),
            }
        ],
        "response": (
            "Server is healthy."
        ),
        "trace_id": "trace-61",
        "execution_trace": {
            "trace_id": "trace-61",
            "user_request": (
                "check cpu "
                "token=super-secret"
            ),
            "answer_strategy": (
                "CANONICAL_AGENT"
            ),
            "system_prompt": (
                "private prompt"
            ),
            "runtime_metrics": {
                "canonical_runtime": {
                    "terminal": "final",
                    "model_calls": 3,
                    "discovery_calls": 1,
                    "action_attempts": 1,
                    "observation_count": 1,
                    "failure": None,
                    "approval_required": False,
                    "budget": {
                        "max_actions": 6,
                        "actions_used": 1,
                        "max_cost": 12,
                        "cost_used": 1,
                    },
                    "api_key": (
                        "super-secret"
                    ),
                    "hidden_reasoning": (
                        "private thoughts"
                    ),
                }
            },
        },
    }

    deps = SimpleNamespace(
        prepare_query=mock.MagicMock(
            return_value=(
                "session-61",
                agent,
                threading.RLock(),
            )
        )
    )

    response = query(
        {
            "question": "check cpu",
            "session_id": "session-61",
            "asked_at": (
                "2026-08-18T08:00:00"
                "+00:00"
            ),
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

    assert (
        response["assessment"]
        == "Server is healthy."
    )
    assert (
        response["trace_id"]
        == "trace-61"
    )

    trace = response[
        "execution_trace"
    ]

    assert isinstance(
        trace,
        dict,
    )
    assert (
        trace["trace_id"]
        == "trace-61"
    )
    assert (
        trace["user_request"]
        == "check cpu token=<redacted>"
    )

    runtime = trace[
        "runtime_metrics"
    ]["canonical_runtime"]

    assert (
        runtime["terminal"]
        == "final"
    )
    assert runtime[
        "model_calls"
    ] == 3
    assert runtime[
        "action_attempts"
    ] == 1

    serialized = json.dumps(
        trace
    )

    assert (
        "super-secret"
        not in serialized
    )
    assert (
        "private prompt"
        not in serialized
    )
    assert (
        "private thoughts"
        not in serialized
    )
    assert (
        "system_prompt"
        not in serialized
    )
    assert (
        "hidden_reasoning"
        not in serialized
    )
    assert (
        "api_key"
        not in serialized
    )


def test_execution_trace_boundary_is_bounded_and_fails_closed() -> None:
    oversized = {
        "trace_id": "large-trace",
        "answer_strategy": (
            "CANONICAL_AGENT"
        ),
        "runtime_metrics": {
            "custom": [
                "x" * 10_000
                for _ in range(100)
            ],
        },
    }

    trace = (
        _sanitize_execution_trace(
            oversized
        )
    )

    assert trace is not None

    encoded = json.dumps(
        trace,
        ensure_ascii=False,
    ).encode("utf-8")

    assert len(encoded) <= (
        128 * 1024
    )
    assert (
        trace["trace_id"]
        == "large-trace"
    )


def test_query_keeps_regeneration_transaction_and_trace_contract() -> None:
    agent = mock.MagicMock()

    snapshot = [
        {
            "role": "user",
            "content": "old",
        }
    ]

    agent.conversation_store.truncate_for_regeneration.return_value = (
        snapshot
    )

    agent.run_with_steps.return_value = {
        "steps": [],
        "response": "regenerated",
        "trace_id": "regen-trace",
        "execution_trace": {
            "trace_id": "regen-trace"
        },
    }

    deps = SimpleNamespace(
        prepare_query=mock.MagicMock(
            return_value=(
                "regen-session",
                agent,
                threading.RLock(),
            )
        )
    )

    response = query(
        {
            "question": "regenerate",
            "session_id": (
                "regen-session"
            ),
            "regenerate_turn_index": 1,
        },
        _request(deps),
    )

    assert (
        response["session_id"]
        == "regen-session"
    )
    assert (
        response["assessment"]
        == "regenerated"
    )
    assert response["steps"] == []
    assert (
        response["trace_id"]
        == "regen-trace"
    )
    assert (
        response["execution_trace"]
        == {
            "trace_id": (
                "regen-trace"
            )
        }
    )

    agent.conversation_store.truncate_for_regeneration.assert_called_once_with(
        1
    )

    agent.conversation_store.restore_messages.assert_not_called()
