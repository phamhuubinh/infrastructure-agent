from __future__ import annotations

import json
import urllib.error
from contextlib import ExitStack
from io import BytesIO

import pytest
from conftest import ScriptedBackend
from fastapi.testclient import TestClient
from test_qa_runner import _runner_mocks
from test_qa_runner import qa_runner as qa_runner

from orion.api.app import create_app
from orion.bootstrap import build_application
from orion.chat.diagnostics import BoundedModelInputDiagnostics
from orion.contracts import (
    AssistantMessage,
    ModelToolCall,
    ModelTurn,
    ToolDefinition,
    ToolError,
    ToolResult,
)
from orion.tool_runtime.registry import ToolRegistration


def read_turns(label: str) -> list[ModelTurn]:
    return [
        ModelTurn(
            tool_calls=(
                ModelToolCall(
                    call_id=f"expand-{label}",
                    tool_name="orion.tools.expand",
                    arguments={"tool_names": ["test.read"]},
                ),
            )
        ),
        ModelTurn(
            tool_calls=(
                ModelToolCall(
                    call_id=f"read-{label}",
                    tool_name="test.read",
                    arguments={},
                ),
            )
        ),
        ModelTurn(assistant=AssistantMessage(content=f"Final {label}.")),
    ]


@pytest.fixture
def public_qa(qa_runner, monkeypatch, tmp_path):  # type: ignore[no-untyped-def]
    """Use the real API/serialization/runtime, but no provider or remote transport."""
    monkeypatch.delenv("ORION_INFRASTRUCTURE_CONFIG", raising=False)
    monkeypatch.setenv("ORION_LOG_PATH", str(tmp_path / "local.log"))
    monkeypatch.setenv("ORION_RUNTIME_DIAGNOSTICS", "qa")
    monkeypatch.setenv("ORION_SYNTHETIC_PASSWORD", "do-not-persist")
    monkeypatch.setattr(
        "orion.bootstrap.BoundedModelInputDiagnostics",
        lambda: BoundedModelInputDiagnostics(text_limit=120, canonical_result_limit=120),
    )
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: pytest.fail("network"))
    stack = ExitStack()

    def setup(turns, *, enabled=True, tool_error=False):  # type: ignore[no-untyped-def]
        if not enabled:
            monkeypatch.delenv("ORION_RUNTIME_DIAGNOSTICS")
        backend = ScriptedBackend(turns)
        definition = ToolDefinition(
            name="test.read",
            description="Read synthetic data.",
            handler_key="test.read",
            input_schema={"type": "object", "properties": {}},
        )
        application = build_application(
            tmp_path / "api.db",
            backend,
            tool_registrations=(
                ToolRegistration(
                    definition=definition,
                    handler=lambda call: ToolResult(
                        call_id=call.call_id,
                        tool_name=call.tool_name,
                        status="error" if tool_error else "success",
                        error=ToolError(code="synthetic", message="Controlled failure")
                        if tool_error
                        else None,
                        data={"password": "do-not-persist", "payload": "x" * 300},
                    ),
                ),
            ),
        )
        stack.callback(application.store.close)
        client = stack.enter_context(TestClient(create_app(application=application)))
        application.store.upsert_model_config(
            "openai_compatible", "http://mock.invalid", "fake", None
        )
        sent = []
        fetched = []

        def request(_, method, path, body=None):  # type: ignore[no-untyped-def]
            response = client.request(method, path, json=body)
            if path.endswith("/diagnostics"):
                fetched.append(path.split("/")[-2])
            if response.is_error:
                raise urllib.error.HTTPError(
                    "http://qa" + path,
                    response.status_code,
                    "synthetic API error",
                    None,
                    BytesIO(response.content),
                )
            payload = response.json()
            if path.endswith("/messages"):
                sent.append((path.split("/")[-2], payload["request_id"]))
            if path.endswith("/timeline"):
                assert all("request_id" not in item for item in payload)
            return payload

        _runner_mocks(qa_runner, monkeypatch)
        monkeypatch.setattr(qa_runner, "_available_port", lambda: 61001)
        monkeypatch.setattr(qa_runner, "_json_request", request)
        return client, backend, sent, fetched

    yield setup
    stack.close()


@pytest.mark.parametrize(
    "scenario",
    [
        "ordinary_chat",
        "multi_turn",
        "continuity",
        "project_shared_document",
        "tool_error_recovery",
    ],
)
def test_public_api_request_identity_reaches_qa_capture(
    qa_runner, public_qa, monkeypatch, tmp_path, scenario
) -> None:  # type: ignore[no-untyped-def]
    multiple = scenario != "ordinary_chat"
    client, backend, sent, fetched = public_qa(
        read_turns("first") + (read_turns("second") if multiple else []),
        tool_error=scenario == "tool_error_recovery",
    )
    if scenario == "project_shared_document":
        # Stub only document checks; retain real project/session/message APIs.
        monkeypatch.setattr(qa_runner, "_attach_and_wait", lambda *a: {"document_id": "doc"})
        monkeypatch.setattr(qa_runner, "_document_source_ids", lambda *a: {"doc"})
    case = qa_runner.Case(
        id="synthetic",
        prompt="read",
        category="qa",
        manual_quality=True,
        scenario=scenario,
        first_prompt="first",
        turns=("second",) if multiple else (),
    )
    checkpoint = qa_runner.ReportCheckpoint(tmp_path / "report", ())
    checkpoint.start({"mode": "full"})

    def stopped(_):  # type: ignore[no-untyped-def]
        persisted = json.loads((checkpoint.report_directory / "cases.partial.jsonl").read_text())
        assert persisted["runtime_input_diagnostics"]  # Captured before process shutdown.

    monkeypatch.setattr(qa_runner, "stop_qa_process", stopped)
    results, _ = qa_runner._run_structured(
        [case], {"base_url": "http://mock.invalid", "id": "fake", "api_key": ""}, False, checkpoint
    )
    result = results[0]
    assert result["status"] == "MANUAL_REVIEW", result
    assert len(sent) == (2 if multiple else 1)
    assert len({request_id for _, request_id in sent}) == len(sent)
    assert fetched == [request_id for _, request_id in sent]
    captures = result["runtime_input_diagnostics"]
    assert [entry["request_id"] for entry in captures] == fetched
    assert [entry["send_index"] for entry in captures] == list(range(1, len(sent) + 1))
    assert [entry["session_id"] for entry in captures] == [session for session, _ in sent]
    assert len({session for session, _ in sent}) == (
        2 if scenario == "project_shared_document" else 1
    )
    for entry in captures:
        expected = client.get(f"/api/requests/{entry['request_id']}/diagnostics").json()
        assert entry["capture"] == expected
        records = expected["records"]
        assert records and all(record["request_id"] == entry["request_id"] for record in records)
        projections = [
            projection
            for record in records
            for projection in record.get("model_input", {}).get("tool_result_projections", [])
        ]
        assert any(p["content_truncated"] for p in projections)
        assert all(len(p["content"].encode()) <= 120 for p in projections)
    assert "do-not-persist" not in json.dumps(result)
    assert len(backend.calls) == (6 if multiple else 3)


@pytest.mark.parametrize(
    "failure", ["disabled", "timeout", "invalid_json", "non_object", "empty", "wrong_request"]
)
def test_optional_diagnostics_failure_does_not_change_execution(
    qa_runner, public_qa, monkeypatch, failure
) -> None:  # type: ignore[no-untyped-def]
    _, _, sent, fetched = public_qa(read_turns("first"), enabled=failure != "disabled")
    original = qa_runner._json_request

    def request(base, method, path, body=None):  # type: ignore[no-untyped-def]
        if path.endswith("/diagnostics") and failure != "disabled":
            fetched.append(path.split("/")[-2])
            if failure == "timeout":
                raise qa_runner.QARequestTimeout()
            if failure == "invalid_json":
                raise json.JSONDecodeError("synthetic", "", 0)
            if failure == "wrong_request":
                return {"records": [{"request_id": "another-request", "content": "not ours"}]}
            return [] if failure == "non_object" else {"records": []}
        return original(base, method, path, body)

    monkeypatch.setattr(qa_runner, "_json_request", request)
    results, _ = qa_runner._run_structured(
        [qa_runner.Case(id="synthetic", prompt="read", category="qa", manual_quality=True)],
        {"base_url": "http://mock.invalid", "id": "fake", "api_key": ""},
        False,
    )
    assert results[0]["status"] == "MANUAL_REVIEW"
    entry = results[0]["runtime_input_diagnostics"][0]
    assert entry["request_id"] == sent[0][1]
    assert fetched == [sent[0][1]]
    assert entry["capture_status"] == "unavailable"
    assert "capture" not in entry
    assert entry["reason"]


def test_second_send_timeout_does_not_borrow_identity_and_next_case_is_independent(
    qa_runner, public_qa, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    _, _, sent, fetched = public_qa(read_turns("first") + read_turns("next-case"))
    original = qa_runner._json_request
    attempts = 0

    def request(base, method, path, body=None):  # type: ignore[no-untyped-def]
        nonlocal attempts
        if path.endswith("/messages"):
            attempts += 1
            if attempts == 2:
                raise qa_runner.QARequestTimeout()
        return original(base, method, path, body)

    monkeypatch.setattr(qa_runner, "_json_request", request)
    results, _ = qa_runner._run_structured(
        [
            qa_runner.Case(
                id="timeout",
                prompt="first",
                turns=("second",),
                scenario="multi_turn",
                category="qa",
                manual_quality=True,
            ),
            qa_runner.Case(id="next", prompt="next", category="qa", manual_quality=True),
        ],
        {"base_url": "http://mock.invalid", "id": "fake", "api_key": ""},
        False,
    )
    assert [result["status"] for result in results] == ["FAIL", "MANUAL_REVIEW"]
    first = results[0]["runtime_input_diagnostics"]
    assert [entry["request_id"] for entry in first] == [sent[0][1], None]
    assert first[1]["capture_status"] == "unavailable" and "capture" not in first[1]
    assert first[1]["session_id"] == sent[0][0] and first[1]["send_index"] == 2
    next_entry = results[1]["runtime_input_diagnostics"][0]
    assert next_entry["request_id"] == sent[1][1] and next_entry["send_index"] == 1
    assert fetched == [request_id for _, request_id in sent]


@pytest.mark.parametrize("scope", [("other", "local"), ("local", "other")])
def test_request_diagnostics_keeps_public_api_security_boundary(public_qa, scope) -> None:  # type: ignore[no-untyped-def]
    client, _, _, _ = public_qa([])
    application = client.app.state.application
    foreign_session = application.store.create_session(*scope)
    foreign_request = application.runtime.begin(foreign_session, "private")
    assert client.get(f"/api/requests/{foreign_request}/diagnostics").status_code == 404
    assert client.get("/api/requests/nonexistent/diagnostics").status_code == 404
