"""Capability loading retains canonical validation and request-local permissions."""

import pytest
from conftest import ScriptedBackend

from orion.bootstrap import build_application
from orion.contracts import AssistantMessage, ModelToolCall, ModelTurn, ToolDefinition, ToolResult
from orion.tool_runtime.registry import ToolRegistration


@pytest.mark.anyio
async def test_lazy_rag_loads_only_requested_schemas_and_cleans_request_state(tmp_path):
    backend = ScriptedBackend(
        [
            ModelTurn(assistant=AssistantMessage(content="Hello")),
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="load",
                        tool_name="tools.enable",
                        arguments={"capabilities": ["knowledge"]},
                    ),
                )
            ),
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="find",
                        tool_name="knowledge.search",
                        arguments={"query": "quartz marker"},
                    ),
                )
            ),
            ModelTurn(assistant=AssistantMessage(content="The marker is QUARTZ-349.")),
            ModelTurn(assistant=AssistantMessage(content="Hello again")),
        ]
    )
    app = build_application(tmp_path / "orion.db", backend, seed_model_from_environment=False)
    app.store.upsert_model_config("openai_compatible", "http://fixture.test", "fixture", None)
    session = app.store.create_session()
    app.knowledge.attach(session, "quartz.txt", b"The quartz marker is QUARTZ-349.")
    try:
        await app.runtime.submit(session, "hello")
        result = await app.runtime.submit(session, "Find the quartz marker in my document")
        assert result.status == "completed" and "QUARTZ-349" in result.assistant_content
        assert [t.name for t in backend.calls[0][1]] == ["tools.enable"]
        assert [t.name for t in backend.calls[1][1]] == ["tools.enable"]
        loaded = {t.name for t in backend.calls[2][1]}
        assert "knowledge.search" in loaded and "knowledge.read" in loaded
        assert "system.command.run" not in loaded and "scheduler.create" not in loaded
        await app.runtime.submit(session, "hello again")
        assert [t.name for t in backend.calls[-1][1]] == ["tools.enable"]
        assert app.runtime._tool_exposure.enabled == {}
    finally:
        await app.commands.close()
        await app.endpoints.close()
        app.store.close()


@pytest.mark.anyio
async def test_loading_mutation_schema_never_grants_execution_permission(tmp_path):
    executions = []
    definition = ToolDefinition(
        name="system.fixture",
        handler_key="system.fixture",
        description="Fixture mutation.",
        operation_kind="mutation",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    )
    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="load",
                        tool_name="tools.enable",
                        arguments={"capabilities": ["commands"]},
                    ),
                )
            ),
            ModelTurn(
                tool_calls=(
                    ModelToolCall(call_id="mutate", tool_name="system.fixture", arguments={}),
                )
            ),
            *[
                ModelTurn(assistant=AssistantMessage(content="Permission is required."))
                for _ in range(4)
            ],
        ]
    )

    def execute(call):
        executions.append(call)
        return ToolResult(call_id=call.call_id, tool_name=call.tool_name, status="success", data={})

    app = build_application(
        tmp_path / "permission.db",
        backend,
        tool_registrations=(ToolRegistration(definition, execute),),
        seed_model_from_environment=False,
    )
    app.store.upsert_model_config("openai_compatible", "http://fixture.test", "fixture", None)
    try:
        result = await app.runtime.submit(app.store.create_session(), "Run the fixture")
        assert result.status == "completed"
        assert executions == []
        assert any(t.name == "system.fixture" for t in backend.calls[1][1])
        assert app.runtime._tool_exposure.enabled == {}
    finally:
        await app.commands.close()
        await app.endpoints.close()
        app.store.close()


@pytest.mark.anyio
async def test_repeated_capability_loading_stalls_and_finishes_without_a_tool_loop(tmp_path):
    from orion.contracts import ModelTurnCompleted
    from orion.models.backend import ModelBackend

    class Repeating(ModelBackend):
        def __init__(self):
            self.calls = 0

        async def stream(self, messages, tools, settings, cancellation):
            self.calls += 1
            if tools:
                turn = ModelTurn(
                    tool_calls=(
                        ModelToolCall(
                            call_id=f"load-{self.calls}",
                            tool_name="tools.enable",
                            arguments={"capabilities": ["calculator"]},
                        ),
                    )
                )
            else:
                turn = ModelTurn(assistant=AssistantMessage(content="No progress is possible."))
            yield ModelTurnCompleted(turn=turn)

    backend = Repeating()
    app = build_application(tmp_path / "loop.db", backend, seed_model_from_environment=False)
    app.store.upsert_model_config("openai_compatible", "http://fixture.test", "fixture", None)
    try:
        result = await app.runtime.submit(app.store.create_session(), "Calculate")
        assert result.status == "completed"
        assert backend.calls <= 6
        assert app.runtime._tool_exposure.enabled == {}
        events = app.store._connection.execute(
            "SELECT count(*) FROM request_events WHERE event_type='recovery.stalled'"
        ).fetchone()[0]
        assert events == 1
    finally:
        await app.commands.close()
        await app.endpoints.close()
        app.store.close()
