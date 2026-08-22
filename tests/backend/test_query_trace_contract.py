from __future__ import annotations

import json
import threading
from types import SimpleNamespace
from unittest import mock

from src.agent.runtime_factory import create_deterministic_agent
from src.backend.routers.query import _sanitize_execution_trace, query
from src.model.assessment_model_adapter import AssessmentModelAdapter
from src.shared.execution.tool_result import ToolResult
from src.tool.capability_result import CapabilityStatus
from src.tool.target_preflight import EnvironmentFingerprint
from tests.fixtures.fake_models import ScriptedAssessmentModel


def _request(deps: object) -> SimpleNamespace:
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(deps=deps)))


def _controller_final(answer: str) -> str:
    return json.dumps(
        {
            "v": 1,
            "k": "final",
            "g": "Answer the request.",
            "c": None,
            "a": None,
            "f": answer,
            "q": None,
            "r": None,
        }
    )


class _QueuedAssessmentModel(AssessmentModelAdapter):
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses

    def assess(self, _request: object) -> str:
        raise AssertionError("configured Agent v2 must use controller calls")

    def assess_raw(self, _prompt: str) -> str:
        return self.responses.pop(0)


def _controller_action(capability_id: str) -> str:
    return json.dumps(
        {
            "v": 1,
            "k": "action",
            "g": "Follow the request.",
            "c": None,
            "a": {"i": capability_id, "a": {}},
            "f": None,
            "q": None,
            "r": None,
        }
    )


def _reachable_monitor(*_args: object, **_kwargs: object) -> EnvironmentFingerprint:
    return EnvironmentFingerprint(
        target="monitor",
        config_hash="test",
        reachable=True,
        backend_type="local",
        os_family="linux",
        init_system="systemd",
        privilege_level="test",
        available_binaries=frozenset({"lscpu"}),
        has_procfs=True,
        has_sysfs=True,
    )


def test_query_runs_configured_v2_final_through_existing_public_contract(
    tmp_path,
) -> None:
    request_secret = "REQUEST_SECRET_SENTINEL"
    final_secret = "FINAL_SECRET_SENTINEL"
    agent = create_deterministic_agent(
        target_store_path=str(tmp_path / "targets.json"),
        assessment_adapter=ScriptedAssessmentModel(
            draft=_controller_final(f"API final. token={final_secret}")
        ),
    )
    deps = SimpleNamespace(
        prepare_query=mock.MagicMock(
            return_value=("session-v2", agent, threading.RLock())
        )
    )

    response = query(
        {
            "question": f"Explain status {request_secret}",
            "session_id": "session-v2",
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
    assert response["session_id"] == "session-v2"
    assert response["assessment"] == "API final. token=<redacted>"
    assert response["steps"] == []
    assert isinstance(response["trace_id"], str)
    trace = response["execution_trace"]
    assert trace is not None
    assert trace["trace_id"] == response["trace_id"]
    assert trace["user_request"] == ""
    controller = trace["runtime_metrics"]["controller_loop"]
    assert controller["final_response_count"] == 1
    assert controller["action_budget"] == {
        "max_actions": 4,
        "actions_used": 0,
        "max_tools": 4,
        "tools_used": 0,
        "soft_search_queries": 3,
        "max_search_queries": 6,
        "search_queries_used": 0,
        "max_fetches": 6,
        "fetches_used": 0,
    }
    assert (
        trace["runtime_metrics"]["model_usage"]["per_call"][0]["purpose"]
        == "controller"
    )
    rendered = json.dumps(response)
    assert request_secret not in rendered
    assert final_secret not in rendered
    assert "controller wire" not in rendered
    assert "system_prompt" not in rendered
    assert "user_prompt" not in rendered


def test_query_projects_configured_v2_action_steps_without_raw_evidence(
    tmp_path,
    monkeypatch,
) -> None:
    target_store = tmp_path / "targets.json"
    target_store.write_text(json.dumps({"targets": {"monitor": {"backend": "local"}}}))
    agent = create_deterministic_agent(
        target_store_path=str(target_store),
        assessment_adapter=_QueuedAssessmentModel(
            [
                _controller_action("host.get_cpu"),
                _controller_action("host.get_cpu"),
                _controller_final("CPU observation for monitor received."),
            ]
        ),
    )
    deps = SimpleNamespace(
        prepare_query=mock.MagicMock(
            return_value=("session-v2-action", agent, threading.RLock())
        )
    )
    raw_evidence = "RAW_EVIDENCE_SENTINEL"

    monkeypatch.setattr(
        "src.tool.target_registry.TargetRegistry.preflight", _reachable_monitor
    )
    monkeypatch.setattr(
        "src.tool.linux_tool.LinuxTool.execute",
        lambda _tool, _arguments: ToolResult(
            success=True,
            data={"logical_cores": 4, "raw_payload": raw_evidence},
            capability_status=CapabilityStatus.VALID,
        ),
    )

    response = query(
        {"question": "Inspect monitor.", "session_id": "session-v2-action"},
        _request(deps),
    )

    assert len(response["steps"]) == 1
    step = response["steps"][0]
    assert step["type"] == "evidence"
    assert step["capability_id"] == "host.get_cpu"
    assert step["status"] == "success"
    assert step["target_id"] == "monitor"
    assert step["source_id"] == "monitor"
    assert step["provenance_references"]
    rendered = json.dumps(response)
    assert raw_evidence not in rendered
    assert "logical_cores" not in json.dumps(step)


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
