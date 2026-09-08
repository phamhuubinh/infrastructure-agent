from __future__ import annotations

from pathlib import Path

import pytest
from conftest import ScriptedBackend

from orion.bootstrap import _internet_client_from_environment, build_application
from orion.contracts import (
    AssistantMessage,
    ModelToolCall,
    ModelTurn,
    RuntimeScope,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from orion.integrations import DuckDuckGoInternetClient, SearxngInternetClient
from orion.integrations.infrastructure import TargetCatalog
from orion.tool_runtime.mutation_authorization import MutationAuthorizationConfigurationError
from orion.tool_runtime.registry import EXPAND_TOOL_NAME, ToolRegistration, ToolRegistryBuilder


def _definition(name: str, handler_key: str) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description="A test tool.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler_key=handler_key,
    )


def _mutation_definition() -> ToolDefinition:
    return ToolDefinition(
        name="linux.fake.mutation",
        description="A test mutation.",
        input_schema={
            "type": "object",
            "properties": {"target_ref": {"type": "string"}},
            "required": ["target_ref"],
            "additionalProperties": False,
        },
        handler_key="linux.fake.mutation",
        operation_kind="mutation",
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
        "internet.fetch",
        "internet.search",
        "knowledge.list_documents",
        "knowledge.read",
        "knowledge.search",
        "knowledge.source_metadata",
    ]
    assert not hasattr(app.registry, "register")
    assert app.runtime._registry is app.registry  # noqa: SLF001 - verifies composition identity.


@pytest.mark.parametrize("configured", ("not-a-number", "0", "301"))
def test_production_bootstrap_rejects_invalid_model_stream_timeout(
    tmp_path, monkeypatch, configured: str
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("ORION_MODEL_STREAM_TIMEOUT_SECONDS", configured)

    with pytest.raises(ValueError, match="ORION_MODEL_STREAM_TIMEOUT_SECONDS"):
        build_application(tmp_path / "orion.db", ScriptedBackend([]))


def test_internet_bootstrap_uses_built_in_default_or_explicit_searxng_override(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("ORION_INTERNET_SEARCH_URL", raising=False)
    assert isinstance(_internet_client_from_environment(), DuckDuckGoInternetClient)

    monkeypatch.setenv("ORION_INTERNET_SEARCH_URL", "https://search.test/api")
    assert isinstance(_internet_client_from_environment(), SearxngInternetClient)


def test_production_bootstrap_denies_mutations_by_default_before_fake_handler(
    tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("ORION_INFRASTRUCTURE_CONFIG", raising=False)
    executions = 0

    def mutate(call: ToolCall) -> ToolResult:
        nonlocal executions
        executions += 1
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status="success",
            data={"target_ref": call.arguments["target_ref"]},
        )

    app = build_application(
        tmp_path / "orion.db",
        ScriptedBackend([]),
        (ToolRegistration(definition=_mutation_definition(), handler=mutate),),
    )
    blocked = app.runtime._runner.run(  # noqa: SLF001 - verifies production composition.
        ModelToolCall(
            call_id="blocked", tool_name="linux.fake.mutation", arguments={"target_ref": "monitor"}
        ),
        RuntimeScope(session_id="session", principal_id="local", workspace_id="local"),
    )

    assert blocked.status == "error"
    assert blocked.error is not None and blocked.error.code == "operation_blocked"
    assert executions == 0


def test_production_bootstrap_allows_only_configured_exact_mutation_target(
    tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    config = tmp_path / "infrastructure.json"
    config.write_text(
        '{"targets":{"linux":[{"target_ref":"monitor","ssh_alias":"monitor"}]},'
        '"mutation_allowlist":[{"tool_name":"linux.fake.mutation","target_ref":"monitor"}]}',
        encoding="utf-8",
    )
    monkeypatch.setenv("ORION_INFRASTRUCTURE_CONFIG", str(config))
    executions = 0

    def mutate(call: ToolCall) -> ToolResult:
        nonlocal executions
        executions += 1
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status="success",
            data={"target_ref": call.arguments["target_ref"]},
        )

    catalog = TargetCatalog.from_mapping(
        {"targets": {"linux": [{"target_ref": "monitor", "ssh_alias": "monitor"}]}}
    )
    app = build_application(
        tmp_path / "orion.db",
        ScriptedBackend([]),
        (ToolRegistration(definition=_mutation_definition(), handler=mutate),),
        infrastructure_catalog=catalog,
    )
    scope = RuntimeScope(session_id="session", principal_id="local", workspace_id="local")
    allowed = app.runtime._runner.run(  # noqa: SLF001 - verifies production composition.
        ModelToolCall(
            call_id="allowed", tool_name="linux.fake.mutation", arguments={"target_ref": "monitor"}
        ),
        scope,
    )
    wrong_target = app.runtime._runner.run(  # noqa: SLF001 - verifies production composition.
        ModelToolCall(
            call_id="wrong", tool_name="linux.fake.mutation", arguments={"target_ref": "other"}
        ),
        scope.model_copy(update={"project_id": "project"}),
    )

    assert allowed.status == "success"
    assert wrong_target.status == "error"
    assert wrong_target.error is not None and wrong_target.error.code == "operation_blocked"
    assert executions == 1


def test_invalid_production_mutation_allowlist_fails_bootstrap(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    config = tmp_path / "infrastructure.json"
    config.write_text('{"mutation_allowlist":[{"tool_name":"unknown","target_ref":"monitor"}]}')
    monkeypatch.setenv("ORION_INFRASTRUCTURE_CONFIG", str(config))

    with pytest.raises(MutationAuthorizationConfigurationError, match="unknown or non-mutation"):
        build_application(tmp_path / "orion.db", ScriptedBackend([]))


def test_environment_model_bootstrap_preserves_existing_saved_profile(
    tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    database = tmp_path / "orion.db"
    monkeypatch.setenv("ORION_MODEL_BASE_URL", "http://qwen.test/v1")
    monkeypatch.setenv("ORION_MODEL_ID", "qwen3-32b")
    first = build_application(database, ScriptedBackend([]))
    first.store.close()

    monkeypatch.setenv("ORION_MODEL_BASE_URL", "http://replacement.test/v1")
    monkeypatch.setenv("ORION_MODEL_ID", "replacement-model")
    restarted = build_application(database, ScriptedBackend([]))

    assert [profile["model_id"] for profile in restarted.store.model_configs()] == ["qwen3-32b"]
    assert restarted.store.active_model_config()["model_id"] == "qwen3-32b"  # type: ignore[index]


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
                tool_calls=(
                    ModelToolCall(
                        call_id="expand",
                        tool_name=EXPAND_TOOL_NAME,
                        arguments={"tool_names": ["fake.scope"]},
                    ),
                )
            ),
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
