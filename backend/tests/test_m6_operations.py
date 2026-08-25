from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

import httpx
import pytest
from conftest import ScriptedBackend

from orion.api.app import create_app
from orion.bootstrap import build_application
from orion.chat.runtime import RequestCancelled, RequestFailed
from orion.contracts import (
    AssistantMessage,
    ModelToolCall,
    ModelTurn,
    SourceRef,
    ToolCall,
    ToolDefinition,
    ToolError,
    ToolResult,
)
from orion.integrations import SearxngInternetClient
from orion.knowledge.ports import Chunk, ParsedDocument
from orion.tool_runtime.registry import ToolRegistration
from orion.tool_runtime.runner import ToolRunner


def _definition() -> ToolDefinition:
    return ToolDefinition(
        name="fake.secret",
        description="Return ORION_TEST_SECRET_TOKEN from /private/test/key.",
        input_schema={
            "type": "object",
            "description": "ORION_TEST_PRIVATE_URL",
            "properties": {},
            "additionalProperties": False,
        },
        handler_key="fake.secret",
    )


class _FailingParser:
    def parse(self, content: bytes, media_type: str | None) -> ParsedDocument:
        raise ValueError("scripted parser failure")


class _EmptyChunker:
    def chunk(self, parsed: ParsedDocument) -> tuple[Chunk, ...]:
        return ()


MARKERS = (
    "real-test-token",
    "https://private.test/private/test/key",
    "ORION_TEST_SECRET_TOKEN",
    "ORION_TEST_PRIVATE_URL",
    "/private/test/key",
)


@pytest.mark.anyio
async def test_restart_preserves_project_timeline_blob_and_reconciles_ingestion(tmp_path) -> None:  # type: ignore[no-untyped-def]
    database = tmp_path / "data" / "orion.db"
    first = build_application(
        database, ScriptedBackend([ModelTurn(assistant=AssistantMessage(content="First answer."))])
    )
    first.store.upsert_model_config("openai_compatible", "http://model.test/v1", "fake", None)
    project = first.projects.create("Durable project")
    session = first.projects.create_session(project["project_id"], "local", "local")
    document = first.knowledge.attach_project(
        project["project_id"], "notes.txt", b"Durable retrieval fact."
    )
    await first.runtime.submit(session, "Remember this")
    first.store.set_document_state(document.document.document_id, "indexing")
    first.store.close()

    restarted = build_application(database, ScriptedBackend([]))
    scope = restarted.runtime._runtime_scope(session)  # noqa: SLF001 - restart contract.
    status = restarted.knowledge.document_status(document.document.document_id, scope)
    assert restarted.store.session_identity(session)["project_id"] == project["project_id"]  # type: ignore[index]
    assert [item.kind for item in restarted.store.timeline(session)] == [
        "user_message",
        "assistant_message",
    ]
    assert status is not None and status["status"] == "ready"
    assert (
        "Durable retrieval fact"
        in restarted.knowledge.read(scope, document.document.document_id).segments[0].text
    )
    assert len(restarted.store.document_segments(document.document.document_id)) == 1


@pytest.mark.parametrize("state", ("uploaded", "parsing", "indexing"))
def test_restart_reconciles_every_incomplete_document_state_idempotently(
    tmp_path, state: str
) -> None:  # type: ignore[no-untyped-def]
    database = tmp_path / f"{state}.db"
    first = build_application(database, ScriptedBackend([]))
    project = first.projects.create("Restart project")
    session = first.projects.create_session(project["project_id"], "local", "local")
    uploaded = first.knowledge.attach_project(project["project_id"], "notes.txt", b"stable fact")
    document_id = uploaded.document.document_id
    scope = first.runtime._runtime_scope(session)  # noqa: SLF001 - lifecycle invariant.
    source_id = first.knowledge.source_for_segment(
        first.knowledge.read(scope, document_id).segments[0]
    ).source_ref_id
    first.store.set_document_state(document_id, state)
    first.store.close()

    restarted = build_application(database, ScriptedBackend([]))
    restarted_scope = restarted.runtime._runtime_scope(session)  # noqa: SLF001
    assert restarted.store.session_identity(session)["project_id"] == project["project_id"]  # type: ignore[index]
    assert restarted.knowledge.document_status(document_id, restarted_scope)["status"] == "ready"  # type: ignore[index]
    segments = restarted.knowledge.read(restarted_scope, document_id).segments
    assert len(segments) == 1
    assert restarted.knowledge.source_for_segment(segments[0]).source_ref_id == source_id
    restarted.store.close()

    repeated = build_application(database, ScriptedBackend([]))
    repeated_scope = repeated.runtime._runtime_scope(session)  # noqa: SLF001
    assert len(repeated.store.document_segments(document_id)) == 1
    assert repeated.knowledge.document_status(document_id, repeated_scope)["status"] == "ready"  # type: ignore[index]


@pytest.mark.parametrize(
    ("parser", "chunker", "expected"),
    ((_FailingParser(), None, "scripted parser failure"), (None, _EmptyChunker(), "no indexable")),
)
def test_restart_reconciliation_records_parser_and_index_failures(
    tmp_path, parser, chunker, expected: str
) -> None:  # type: ignore[no-untyped-def]
    database = tmp_path / f"failure-{expected}.db"
    first = build_application(database, ScriptedBackend([]))
    project = first.projects.create("Failure project")
    session = first.projects.create_session(project["project_id"], "local", "local")
    uploaded = first.knowledge.attach_project(project["project_id"], "notes.txt", b"stable fact")
    document_id = uploaded.document.document_id
    first.store.store_parsed_document(document_id, "", [])
    first.store.set_document_state(document_id, "parsing" if parser else "indexing")
    first.store.close()

    restarted = build_application(
        database, ScriptedBackend([]), knowledge_parser=parser, knowledge_chunker=chunker
    )
    scope = restarted.runtime._runtime_scope(session)  # noqa: SLF001
    status = restarted.knowledge.document_status(document_id, scope)
    assert status is not None and status["status"] == "failed"
    assert expected in str(status["error_message"])
    assert restarted.store.session_identity(session)["project_id"] == project["project_id"]  # type: ignore[index]
    assert restarted.store.document_segments(document_id) == []


def test_tombstoned_incomplete_document_is_never_resurrected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    database = tmp_path / "tombstone.db"
    first = build_application(database, ScriptedBackend([]))
    project = first.projects.create("Tombstone project")
    session = first.projects.create_session(project["project_id"], "local", "local")
    uploaded = first.knowledge.attach_project(project["project_id"], "notes.txt", b"stable fact")
    document_id = uploaded.document.document_id
    first.store.set_document_state(document_id, "indexing")
    assert first.store.delete_document(document_id)
    events_before = first.store.document_ingestion_events(document_id)
    first.store.close()

    restarted = build_application(database, ScriptedBackend([]))
    assert restarted.store.document(document_id) is None
    assert restarted.store.document(document_id, include_deleted=True)["status"] == "indexing"  # type: ignore[index]
    assert restarted.store.document_ingestion_events(document_id) == events_before
    assert restarted.store.session_identity(session)["project_id"] == project["project_id"]  # type: ignore[index]


@pytest.mark.anyio
async def test_tool_results_events_context_and_logs_redact_configured_markers(
    tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("ORION_TEST_SECRET_TOKEN", "real-test-token")
    monkeypatch.setenv("ORION_TEST_PRIVATE_URL", "https://private.test/private/test/key")
    log_path = tmp_path / "orion.log"
    monkeypatch.setenv("ORION_LOG_PATH", str(log_path))

    def handler(call: ToolCall) -> ToolResult:
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status="success",
            data={
                "token": "real-test-token",
                "url": "https://private.test/private/test/key",
                "marker": "ORION_TEST_SECRET_TOKEN",
            },
        )

    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(ModelToolCall(call_id="secret", tool_name="fake.secret", arguments={}),)
            ),
            ModelTurn(assistant=AssistantMessage(content="Done.")),
        ]
    )
    app = build_application(
        tmp_path / "orion.db",
        backend,
        (ToolRegistration(definition=_definition(), handler=handler),),
    )
    app.store.upsert_model_config("openai_compatible", "http://model.test/v1", "fake", None)
    session = app.store.create_session()
    outcome = await app.runtime.submit(session, "Use the test tool")
    public = "\n".join(
        [
            str(app.registry.definitions()),
            str(app.store.timeline(session)),
            str(app.store.events(outcome.request_id)),
            str(backend.calls),
            log_path.read_text(encoding="utf-8"),
        ]
    )
    for marker in MARKERS:
        assert marker not in public


@pytest.mark.anyio
async def test_public_marker_boundaries_cover_errors_sources_citations_apis_logs_and_context(
    tmp_path, monkeypatch, capsys
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("ORION_TEST_SECRET_TOKEN", "real-test-token")
    monkeypatch.setenv("ORION_TEST_PRIVATE_URL", "https://private.test/private/test/key")
    log_path = tmp_path / "orion.log"
    monkeypatch.setenv("ORION_LOG_PATH", str(log_path))

    def handler(call: ToolCall) -> ToolResult:
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status="error",
            error=ToolError(code="marker", message="ORION_TEST_SECRET_TOKEN /private/test/key"),
            sources=(
                SourceRef(
                    source_ref_id="ORION_TEST_SECRET_TOKEN",
                    source_kind="internet",
                    source_id="ORION_TEST_PRIVATE_URL",
                    label="/private/test/key",
                    url="https://private.test/private/test/key",
                ),
            ),
        )

    app = build_application(
        tmp_path / "markers.db",
        ScriptedBackend([ModelTurn(assistant=AssistantMessage(content="done"))]),
        (ToolRegistration(definition=_definition(), handler=handler),),
        internet_client=SearxngInternetClient(
            "https://private.test/private/test/key",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"results": []})
            ),
        ),
    )
    app.store.upsert_model_config(
        "openai_compatible",
        "https://real-test-token@private.test/private/test/key",
        "ORION_TEST_PRIVATE_URL",
        "real-test-token",
    )
    project = app.projects.create(
        "Marker project",
        "ORION_TEST_SECRET_TOKEN",
        "/private/test/key",
        {"url": "ORION_TEST_PRIVATE_URL"},
    )
    session = app.projects.create_session(project["project_id"], "local", "local")
    scope = app.runtime._runtime_scope(session)  # noqa: SLF001 - direct public boundary proof.
    result = ToolRunner(app.registry).run(
        ModelToolCall(call_id="marker", tool_name="fake.secret", arguments={}), scope
    )
    assert result.status == "error"
    request_id = app.store.create_request(session)
    app.runtime._persist_assistant_turn(  # noqa: SLF001 - persisted public citation representation.
        session,
        request_id,
        ModelTurn(
            assistant=AssistantMessage(
                content="ORION_TEST_SECRET_TOKEN", citation_source_ref_ids=("/private/test/key",)
            )
        ),
    )
    app.runtime._emit(request_id, "marker.event", {"message": "ORION_TEST_PRIVATE_URL"})  # noqa: SLF001
    context = app.runtime._context_builder.build(session)  # noqa: SLF001
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(application=app)), base_url="http://test"
    ) as client:
        integration = await client.get("/api/integrations/internet")
        models = await client.get("/api/models")
    from orion.cli import _show_log

    _show_log(log_path, tmp_path / "markers.db", 100)
    public = "\n".join(
        (
            str(app.registry.definitions()),
            str(result),
            str(context),
            str(app.store.timeline(session)),
            str(app.store.events(request_id)),
            integration.text,
            models.text,
            log_path.read_text(encoding="utf-8"),
            capsys.readouterr().out,
        )
    )
    for marker in MARKERS:
        assert marker not in public


@pytest.mark.anyio
async def test_runtime_terminal_requests_clear_cancellation_registries(tmp_path) -> None:  # type: ignore[no-untyped-def]
    complete = build_application(
        tmp_path / "complete.db",
        ScriptedBackend([ModelTurn(assistant=AssistantMessage(content="done"))]),
    )
    complete.store.upsert_model_config("openai_compatible", "http://model.test", "fake", None)
    complete_session = complete.store.create_session()
    await complete.runtime.submit(complete_session, "complete")
    assert not complete.runtime._cancellations and not complete.runtime._pending_content  # noqa: SLF001

    failed = build_application(tmp_path / "failed.db", ScriptedBackend([]))
    failed.store.upsert_model_config("openai_compatible", "http://model.test", "fake", None)
    with pytest.raises(RequestFailed):
        await failed.runtime.submit(failed.store.create_session(), "fail")
    assert not failed.runtime._cancellations and not failed.runtime._pending_content  # noqa: SLF001

    cancelled = build_application(
        tmp_path / "cancelled.db",
        ScriptedBackend([ModelTurn(assistant=AssistantMessage(content="unused"))]),
    )
    cancelled.store.upsert_model_config("openai_compatible", "http://model.test", "fake", None)
    cancellation = __import__("asyncio").Event()
    cancellation.set()
    with pytest.raises(RequestCancelled):
        await cancelled.runtime.submit(cancelled.store.create_session(), "cancel", cancellation)
    assert not cancelled.runtime._cancellations and not cancelled.runtime._pending_content  # noqa: SLF001


def _free_port() -> int:
    try:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            return int(listener.getsockname()[1])
    except PermissionError:
        pytest.skip("local loopback sockets are unavailable in this execution sandbox")


def _request(url: str, method: str = "GET") -> dict[str, object]:
    request = Request(url, method=method)
    with urlopen(request, timeout=1) as response:  # noqa: S310 - loopback smoke only.
        return json.loads(response.read())


def _wait_for_health(port: int) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            if _request(f"http://127.0.0.1:{port}/api/health")["status"] == "ok":
                return
        except (URLError, TimeoutError, ConnectionError):
            time.sleep(0.05)
    raise AssertionError("Orion web did not bind loopback in time")


def test_cli_loopback_restart_and_redacted_log_smoke(tmp_path) -> None:  # type: ignore[no-untyped-def]
    data, home = tmp_path / "data", tmp_path / "home"
    port = _free_port()
    environment = {**os.environ, "HOME": str(home), "ORION_TEST_SECRET_TOKEN": "do-not-print"}
    command = [
        sys.executable,
        "-m",
        "orion.cli",
        "web",
        "--data-dir",
        str(data),
        "--port",
        str(port),
    ]
    process = subprocess.Popen(
        command, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    try:
        _wait_for_health(port)
        session = _request(f"http://127.0.0.1:{port}/api/sessions", "POST")["session_id"]
    finally:
        process.terminate()
        process.wait(timeout=5)

    process = subprocess.Popen(
        command, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    try:
        _wait_for_health(port)
        persisted = _request(f"http://127.0.0.1:{port}/api/sessions/{session}")
    finally:
        process.terminate()
        process.wait(timeout=5)
    output = subprocess.check_output(
        [sys.executable, "-m", "orion.cli", "log", "--data-dir", str(data)],
        env=environment,
        text=True,
    )
    assert persisted["session_id"] == session
    assert str(data / "orion.db") in output
    assert "do-not-print" not in output
