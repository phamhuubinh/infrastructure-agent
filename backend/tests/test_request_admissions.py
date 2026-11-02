"""One durable admission means one runtime execution, including retry after restart."""

import asyncio
import uuid

import pytest
from conftest import ScriptedBackend

from orion.access import LocalAccessAdapter
from orion.application.requests import RequestAdmissionError, RequestService
from orion.bootstrap import build_application
from orion.chat.runtime import ChatRuntime
from orion.contracts import (
    AssistantMessage,
    ModelToolCall,
    ModelTurn,
    MutationMode,
    RuntimeScope,
    ToolDefinition,
    ToolResult,
)
from orion.persistence.sqlite import SQLiteStore
from orion.tool_runtime.registry import ToolRegistryBuilder


def scope(store, **identity):
    return RuntimeScope(
        session_id=store.create_session(**identity),
        principal_id=identity.get("principal_id", "local"),
        workspace_id=identity.get("workspace_id", "local"),
    )


@pytest.mark.anyio
async def test_repeated_admission_never_repeats_actual_canonical_mutation(store):
    executions = []
    builder = ToolRegistryBuilder()
    builder.register(
        ToolDefinition(
            name="fixture.change",
            handler_key="fixture.change",
            description="Fixture mutation",
            operation_kind="mutation",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        lambda call: (
            executions.append(call.call_id),
            ToolResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                status="success",
                data={"changed": True},
            ),
        )[1],
    )
    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(call_id="once", tool_name="fixture.change", arguments={}),
                )
            ),
            ModelTurn(assistant=AssistantMessage(content="Changed once.")),
        ]
    )
    runtime = ChatRuntime(store, backend, builder.freeze(), LocalAccessAdapter())
    service = RequestService(store, runtime, LocalAccessAdapter())
    owner = scope(store)
    store.set_session_mutation_mode(owner.session_id, MutationMode.AUTO)
    key = str(uuid.uuid4())
    identity, created = service.admit(owner, "Make exactly one change", key)
    task = service.tasks[identity]
    assert created
    assert service.admit(owner, "Make exactly one change", key) == (identity, False)
    await task
    assert service.admit(owner, "Make exactly one change", key) == (identity, False)
    assert executions == ["once"] and len(backend.calls) == 2
    assert store._connection.execute("SELECT count(*) FROM requests").fetchone()[0] == 1
    for other_scope, text in (
        (owner, "Changed payload"),
        (scope(store), "Make exactly one change"),
    ):
        with pytest.raises(RequestAdmissionError, match="identity_conflict"):
            service.admit(other_scope, text, key)
    await service.close()


@pytest.mark.anyio
async def test_admission_rejects_forged_scope_and_foreign_actual_owner(store):
    from conftest import runtime

    service = RequestService(store, runtime(store, ScriptedBackend([])), LocalAccessAdapter())
    owner = scope(store)
    for invalid in (
        owner.model_copy(update={"project_id": "forged"}),
        scope(store, principal_id="foreign"),
    ):
        with pytest.raises(RequestAdmissionError, match="scope"):
            service.admit(invalid, "work", str(uuid.uuid4()))
    assert store._connection.execute("SELECT count(*) FROM requests").fetchone()[0] == 0
    await service.close()


@pytest.mark.anyio
async def test_recovered_interrupted_admission_returns_old_outcome_without_replay(tmp_path):
    path = tmp_path / "orion.db"
    first = SQLiteStore(path)
    owner = scope(first)
    key = str(uuid.uuid4())
    digest = RequestService._identity(owner, "Lost before execution", key)
    identity, created = first.admit_request(owner, key, digest)
    assert created
    first.close()
    backend = ScriptedBackend([])
    application = build_application(path, backend, seed_model_from_environment=False)
    try:
        assert application.store.request(identity)["status"] == "failed"
        service = RequestService(application.store, application.runtime, application.access)
        assert service.admit(owner, "Lost before execution", key) == (identity, False)
        assert not service.tasks and not backend.calls
        await service.close()
    finally:
        application.store.close()


@pytest.mark.anyio
async def test_application_shutdown_cancels_owned_admitted_requests_and_cleans_runtime(store):
    entered = asyncio.Event()

    class WaitingBackend(ScriptedBackend):
        async def stream(self, messages, tools, settings, cancellation):
            entered.set()
            await asyncio.Event().wait()
            yield

    from conftest import runtime

    engine = runtime(store, WaitingBackend([]))
    service = RequestService(store, engine, LocalAccessAdapter())
    identity, _ = service.admit(scope(store), "Wait for Stop", str(uuid.uuid4()))
    await asyncio.wait_for(entered.wait(), 5)
    await asyncio.wait_for(service.close(), 5)
    assert store.request(identity)["status"] == "cancelled"
    assert not service.tasks and not engine._pending_content
