from __future__ import annotations

from pathlib import Path

import pytest
from conftest import ScriptedBackend

from orion.bootstrap import build_application
from orion.contracts import (
    AssistantMessage,
    ModelToolCall,
    ModelTurn,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from orion.tool_runtime.registry import ToolRegistration, ToolRegistryBuilder


def _definition(name: str, handler_key: str) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description="A test tool.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler_key=handler_key,
    )


def test_backend_package_exists_only_in_approved_backend_layout() -> None:
    repository = Path(__file__).resolve().parents[2]
    assert list((repository / "src" / "orion").rglob("*.py")) == []
    import orion

    assert "/backend/src/orion/" in str(Path(orion.__file__).resolve())


def test_registry_builder_rejects_duplicate_names_handler_keys_and_invalid_schemas() -> None:
    builder = ToolRegistryBuilder()
    builder.register(_definition("fake.one", "fake.one"), lambda _call: {})
    with pytest.raises(ValueError, match="duplicate tool name"):
        builder.register(_definition("fake.one", "fake.two"), lambda _call: {})
    with pytest.raises(ValueError, match="duplicate handler key"):
        builder.register(_definition("fake.two", "fake.one"), lambda _call: {})
    with pytest.raises(ValueError, match="invalid JSON Schema"):
        builder.register(
            ToolDefinition(
                name="fake.invalid",
                description="Invalid.",
                input_schema={"type": "object", "properties": {"bad": {"type": 4}}},
                handler_key="fake.invalid",
            ),
            lambda _call: {},
        )


def test_bootstrap_builds_one_immutable_registry_snapshot(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = build_application(tmp_path / "orion.db", ScriptedBackend([]))

    assert [definition.name for definition in app.registry.definitions()] == [
        "calculator.evaluate",
        "knowledge.list_documents",
        "knowledge.read",
        "knowledge.search",
        "knowledge.source_metadata",
    ]
    assert not hasattr(app.registry, "register")
    assert app.runtime._registry is app.registry  # noqa: SLF001 - verifies composition identity.


@pytest.mark.anyio
async def test_local_principal_and_workspace_are_runtime_owned_not_model_arguments(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    seen_call: ToolCall | None = None

    def inspect_scope(call: ToolCall) -> ToolResult:
        nonlocal seen_call
        seen_call = call
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status="success",
            data={"ok": True},
        )

    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(ModelToolCall(call_id="scope-1", tool_name="fake.scope", arguments={}),)
            ),
            ModelTurn(assistant=AssistantMessage(content="Done.")),
        ]
    )
    app = build_application(
        tmp_path / "orion.db",
        backend,
        (
            ToolRegistration(
                definition=_definition("fake.scope", "fake.scope"), handler=inspect_scope
            ),
        ),
    )
    app.store.upsert_model_config("openai_compatible", "http://model.test/v1", "fake", None)
    principal = app.access.current_principal()
    session_id = app.store.create_session(principal.principal_id, principal.workspace_id)

    await app.runtime.submit(session_id, "Inspect my access")

    assert seen_call is not None
    assert seen_call.arguments == {}
    assert seen_call.runtime_scope.principal_id == "local"
    assert seen_call.runtime_scope.workspace_id == "local"
    assert "local" not in backend.calls[0][0][-1].content
