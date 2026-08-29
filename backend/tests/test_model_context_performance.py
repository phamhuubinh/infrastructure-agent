from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from conftest import ScriptedBackend, runtime

from orion.chat.context_builder import MAX_CONVERSATION_BYTES, ContextBuilder, _messages_bytes
from orion.chat.model_context import project_tool_result
from orion.contracts import (
    AssistantMessage,
    ContextMessage,
    ModelToolCall,
    ModelTurn,
    SourceRef,
    ToolCall,
    ToolResult,
)
from orion.knowledge.tools import (
    list_documents_definition,
    read_definition,
    search_definition,
    source_metadata_definition,
)
from orion.models.providers.openai_compatible import OpenAICompatibleBackend
from orion.tool_runtime.calculator import calculator_definition
from orion.tool_runtime.infrastructure import infrastructure_definitions
from orion.tool_runtime.internet import internet_fetch_definition, internet_search_definition
from orion.tool_runtime.registry import EXPAND_TOOL_NAME, ToolRegistryBuilder

EXPECTED_PROVIDER_TOOL_SCHEMA_BYTES = 10_628
EXPECTED_SIMPLE_PROXY_BYTES = 12_501
EXPECTED_CATALOG_BYTES = 617
EXPECTED_EXPANSION_SCHEMA_BYTES = 301
EXPECTED_PROGRESSIVE_INITIAL_PROXY_BYTES = 2_000
EXPECTED_PROGRESSIVE_ONE_TOOL_PROXY_BYTES = 2_268
EXPECTED_PROGRESSIVE_THREE_TOOL_PROXY_BYTES = 3_147
EXPECTED_ZABBIX_EXPANSION_PROXY_BYTES = 3_030
EXPECTED_ZABBIX_RESUMED_PROXY_BYTES = 9_220
BASELINE_ZABBIX_RESUME_PROXY_BYTES = 32_963
BASELINE_HISTORY_PROXY_BYTES = 69_093


def _all_definitions():  # type: ignore[no-untyped-def]
    return tuple(
        sorted(
            (
                calculator_definition(),
                internet_fetch_definition(),
                internet_search_definition(),
                list_documents_definition(),
                read_definition(),
                search_definition(),
                source_metadata_definition(),
                *infrastructure_definitions(),
            ),
            key=lambda definition: definition.name,
        )
    )


def _zabbix_result(call_id: str = "zabbix-1") -> ToolResult:
    events = [
        {
            "event_id": str(100_000 + index),
            "name": f"Production DB latency threshold exceeded on db-{index % 4}",
            "severity": ("warning", "average", "high", "disaster")[index % 4],
            "acknowledged": index % 3 == 0,
            "clock": str(1_724_000_000 + index * 60),
        }
        for index in range(100)
    ]
    return ToolResult(
        call_id=call_id,
        tool_name="zabbix.event.list",
        status="success",
        data={"target_ref": "zabbix", "results": events},
        sources=(
            SourceRef(
                source_ref_id="zabbix-events-prod",
                source_kind="zabbix",
                source_id="zabbix",
                section="list",
                label="Production Zabbix",
                retrieved_at=datetime(2026, 8, 28, tzinfo=UTC),
            ),
        ),
    )


def _provider_proxy(messages) -> int:  # type: ignore[no-untyped-def]
    payload = {
        "messages": [OpenAICompatibleBackend._message_payload(message) for message in messages],
        "tools": [definition.provider_schema() for definition in _all_definitions()],
    }
    return len(json.dumps(payload, sort_keys=True).encode())


def _compact_provider_proxy(messages, tools) -> int:  # type: ignore[no-untyped-def]
    payload = {
        "messages": [OpenAICompatibleBackend._message_payload(message) for message in messages],
        "tools": [definition.provider_schema() for definition in tools],
    }
    return len(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())


def _append_zabbix_exchange(store, session_id: str, result: ToolResult) -> None:  # type: ignore[no-untyped-def]
    call = ModelToolCall(
        call_id=result.call_id,
        tool_name=result.tool_name,
        arguments={"target_ref": "zabbix"},
    )
    store.append_timeline(
        session_id,
        None,
        "assistant_message",
        {
            "content": "",
            "citation_source_ref_ids": [],
            "tool_calls": [call.model_dump(mode="json")],
        },
    )
    store.append_timeline(
        session_id,
        None,
        "tool_call",
        {"arguments": call.arguments, "operation_kind": "read"},
        call_id=call.call_id,
        tool_name=call.tool_name,
    )
    store.append_timeline(
        session_id,
        None,
        "tool_result",
        {"result": result.model_dump(mode="json")},
        call_id=result.call_id,
        tool_name=result.tool_name,
    )


def test_provider_tool_schema_size_and_simple_context_regressions(store) -> None:  # type: ignore[no-untyped-def]
    definitions = _all_definitions()
    provider_schemas = [item.provider_schema() for item in definitions]
    schema_bytes = len(json.dumps(provider_schemas, separators=(",", ":")).encode())
    assert len(definitions) == 25
    assert schema_bytes == EXPECTED_PROVIDER_TOOL_SCHEMA_BYTES
    assert {schema["function"]["name"] for schema in provider_schemas} == {
        definition.name for definition in definitions
    }
    model_visible = json.dumps(provider_schemas)
    for internal_field in (
        "handler_key",
        "credential_ref",
        "api_key",
        "password",
        "runtime_scope",
        "principal_id",
        "workspace_id",
    ):
        assert internal_field not in model_visible

    session_id = store.create_session()
    store.append_timeline(session_id, None, "user_message", {"content": "Hello"})
    simple_proxy = _provider_proxy(ContextBuilder(store).build(session_id))
    assert simple_proxy == EXPECTED_SIMPLE_PROXY_BYTES


def test_progressive_model_view_size_regressions(store) -> None:  # type: ignore[no-untyped-def]
    definitions = _all_definitions()
    builder = ToolRegistryBuilder()
    for definition in definitions:
        builder.register(
            definition,
            lambda call: ToolResult(
                call_id=call.call_id, tool_name=call.tool_name, status="success", data={}
            ),
        )
    exposure = builder.freeze().new_tool_exposure()
    session_id = store.create_session()
    store.append_timeline(session_id, None, "user_message", {"content": "Hello"})
    messages = ContextBuilder(store).build(session_id)
    model_messages = (*messages, ContextMessage(role="system", content=exposure.catalog))

    assert exposure.catalog.splitlines() == [
        (
            "Tools (expand exact ordinary names with orion.tools.expand before execution; "
            "expansion is additive and repeatable):"
        ),
        *(definition.name for definition in definitions),
    ]
    assert len(exposure.catalog.encode()) == EXPECTED_CATALOG_BYTES
    assert (
        len(json.dumps(exposure.model_tools[0].provider_schema(), separators=(",", ":")).encode())
        == EXPECTED_EXPANSION_SCHEMA_BYTES
    )
    assert _compact_provider_proxy(messages, definitions) == 11_652
    assert _compact_provider_proxy(model_messages, exposure.model_tools) == (
        EXPECTED_PROGRESSIVE_INITIAL_PROXY_BYTES
    )

    exposure.expand(
        ModelToolCall(
            call_id="one",
            tool_name=EXPAND_TOOL_NAME,
            arguments={"tool_names": ["calculator.evaluate"]},
        )
    )
    assert _compact_provider_proxy(model_messages, exposure.model_tools) == (
        EXPECTED_PROGRESSIVE_ONE_TOOL_PROXY_BYTES
    )
    exposure.expand(
        ModelToolCall(
            call_id="more",
            tool_name=EXPAND_TOOL_NAME,
            arguments={"tool_names": ["internet.search", "zabbix.event.list"]},
        )
    )
    assert _compact_provider_proxy(model_messages, exposure.model_tools) == (
        EXPECTED_PROGRESSIVE_THREE_TOOL_PROXY_BYTES
    )


def test_realistic_resumed_turn_is_bounded_and_canonical_result_stays_full(store) -> None:  # type: ignore[no-untyped-def]
    session_id = store.create_session()
    store.append_timeline(session_id, None, "user_message", {"content": "List events"})
    result = _zabbix_result()
    assert 14_000 < len(result.model_dump_json().encode()) < 15_000
    _append_zabbix_exchange(store, session_id, result)

    context = ContextBuilder(store).build(session_id)
    model_result = json.loads(context[-1].content)
    resumed_proxy = _provider_proxy(context)

    assert resumed_proxy == 18_719
    assert resumed_proxy < BASELINE_ZABBIX_RESUME_PROXY_BYTES
    assert resumed_proxy <= 23_000
    assert len(context[-1].content.encode()) <= 6_000
    assert model_result["_orion_projection"]["applied"] is True
    assert model_result["data"]["target_ref"] == "zabbix"
    assert model_result["_orion_projection"]["omissions"]
    persisted = store.timeline(session_id)[-1].payload["result"]
    assert persisted == result.model_dump(mode="json")
    assert len(persisted["data"]["results"]) == 100
    assert "_orion_projection" not in persisted


def test_many_current_tool_results_share_one_aggregate_budget_and_keep_all_pairs(store) -> None:  # type: ignore[no-untyped-def]
    session_id = store.create_session()
    store.append_timeline(
        session_id, None, "user_message", {"content": "Compare every current result"}
    )
    for index in range(10):
        result = ToolResult(
            call_id=f"generic-{index}",
            tool_name="fake.generic",
            status="success",
            data={
                "target_ref": f"target-{index}",
                "results": [
                    {"index": item, "text": f"result-{index}-" + "x" * 400} for item in range(40)
                ],
            },
        )
        _append_zabbix_exchange(store, session_id, result)

    context = ContextBuilder(store).build(session_id)
    first_user = next(index for index, message in enumerate(context) if message.role == "user")
    current_messages = context[first_user:]

    assert _messages_bytes(current_messages) <= MAX_CONVERSATION_BYTES
    assistants = [message for message in current_messages if message.tool_calls]
    tool_messages = [message for message in current_messages if message.role == "tool"]
    assert len(assistants) == len(tool_messages) == 10
    assert [message.tool_calls[0].call_id for message in assistants] == [
        message.tool_call_id for message in tool_messages
    ]
    for index, message in enumerate(current_messages):
        if not message.tool_calls:
            continue
        assistant_payload = OpenAICompatibleBackend._message_payload(message)
        tool_payload = OpenAICompatibleBackend._message_payload(current_messages[index + 1])
        assert tool_payload["role"] == "tool"
        assert tool_payload["tool_call_id"] == assistant_payload["tool_calls"][0]["id"]
    projections = [json.loads(message.content) for message in tool_messages]
    assert {projection["data"]["target_ref"] for projection in projections} == {
        f"target-{index}" for index in range(10)
    }
    assert (
        len({projection["_orion_projection"]["maximum_bytes"] for projection in projections}) == 1
    )
    for projection in projections:
        collection = next(
            omission
            for omission in projection["_orion_projection"]["omissions"]
            if omission["path"] == "$.data.results"
        )
        assert collection["original_items"] == 40
        assert collection["included_items"] + collection["omitted_items"] == 40
    assert _messages_bytes(current_messages) == 10_508
    assert _provider_proxy(context) == 23_464


def test_projection_preserves_collection_counts_when_large_details_precede_records() -> None:
    result = ToolResult(
        call_id="records-1",
        tool_name="fake.mutation",
        status="success",
        data={
            "target_ref": "production",
            "changed": True,
            "verification": {"status": "verified", "details": "v" * 5_000},
            "records": [{"id": index} for index in range(37)],
        },
    )

    projected = json.loads(project_tool_result(result, 1_500))
    record_omission = next(
        omission
        for omission in projected["_orion_projection"]["omissions"]
        if omission["path"] == "$.data.records"
    )

    assert projected["data"]["verification"]["status"] == "verified"
    assert record_omission["original_items"] == 37
    assert record_omission["included_items"] + record_omission["omitted_items"] == 37


def test_projection_reports_when_omission_metadata_is_itself_bounded() -> None:
    result = ToolResult(
        call_id="many-omissions",
        tool_name="fake.read",
        status="success",
        data={f"collection_{index}": ["x" * 1_000] * 5 for index in range(30)},
    )

    projected = json.loads(project_tool_result(result, 1_500))
    metadata = projected["_orion_projection"]

    assert len(metadata["omissions"]) <= 12
    assert metadata["omission_entries_omitted"] > 0


def test_projection_preserves_exact_sources_errors_and_mutation_metadata() -> None:
    source = _zabbix_result().sources[0]
    result = ToolResult(
        call_id="mutation-1",
        tool_name="fake.mutation",
        status="success",
        data={
            "target_ref": "production",
            "changed": True,
            "verification": {"status": "verified", "details": "x" * 5_000},
            "records": [{"value": "y" * 500} for _ in range(20)],
        },
        sources=(source,),
    )

    projected = json.loads(project_tool_result(result, 1_500))

    assert len(project_tool_result(result, 1_500).encode()) <= 1_500
    assert projected["call_id"] == "mutation-1"
    assert projected["status"] == "success"
    assert projected["data"]["target_ref"] == "production"
    assert projected["data"]["changed"] is True
    assert projected["data"]["verification"]["status"] == "verified"
    assert projected["sources"] == [source.model_dump(mode="json")]

    failed = ToolResult.failure("failed-1", "fake.read", "upstream_error", "Bounded public error.")
    projected_failure = json.loads(project_tool_result(failed, 1_500))
    assert projected_failure["status"] == "error"
    assert projected_failure["error"] == failed.error.model_dump(mode="json")


def test_historical_growth_is_bounded_by_complete_recent_turns(store) -> None:  # type: ignore[no-untyped-def]
    session_id = store.create_session()
    store.append_timeline(session_id, None, "user_message", {"content": "List events"})
    _append_zabbix_exchange(store, session_id, _zabbix_result())
    for turn in range(30):
        store.append_timeline(
            session_id,
            None,
            "assistant_message",
            {
                "content": f"Answer {turn}: " + "detail " * 100,
                "citation_source_ref_ids": [],
                "tool_calls": [],
            },
        )
        store.append_timeline(
            session_id,
            None,
            "user_message",
            {"content": f"Follow-up question {turn}: " + "context " * 50},
        )

    context = ContextBuilder(store).build(session_id)
    history_proxy = _provider_proxy(context)

    assert history_proxy == 24_012
    assert history_proxy < BASELINE_HISTORY_PROXY_BYTES
    assert history_proxy <= 28_000
    assert any("canonical session timeline remains complete" in item.content for item in context)
    users = [item.content for item in context if item.role == "user"]
    assert users[-1].startswith("Follow-up question 29:")
    assert all(item.content for item in context if item.role == "user")
    assert len(store.timeline(session_id)) == 64


def test_huge_historical_tool_turn_is_skipped_without_cutting_older_complete_turns(store) -> None:  # type: ignore[no-untyped-def]
    session_id = store.create_session()
    store.append_timeline(session_id, None, "user_message", {"content": "Older valid question"})
    store.append_timeline(
        session_id,
        None,
        "assistant_message",
        {"content": "Older valid answer", "citation_source_ref_ids": [], "tool_calls": []},
    )
    store.append_timeline(session_id, None, "user_message", {"content": "Huge tool turn"})
    for index in range(70):
        _append_zabbix_exchange(store, session_id, _zabbix_result(f"historical-{index}"))
    store.append_timeline(
        session_id,
        None,
        "assistant_message",
        {"content": "Huge turn answer", "citation_source_ref_ids": [], "tool_calls": []},
    )
    store.append_timeline(session_id, None, "user_message", {"content": "Current question"})

    loaded, omitted_at_read = store.model_context_timeline(session_id)
    context = ContextBuilder(store).build(session_id)
    users = [message.content for message in context if message.role == "user"]

    assert loaded[0].kind == "user_message"
    assert loaded[0].payload["content"] == "Older valid question"
    assert omitted_at_read == 0
    assert users == ["Older valid question", "Current question"]
    assert any("Omitted turns: 1" in message.content for message in context)


def test_model_context_query_does_not_deserialize_unbounded_old_timeline(store) -> None:  # type: ignore[no-untyped-def]
    session_id = store.create_session()
    for turn in range(150):
        store.append_timeline(
            session_id, None, "user_message", {"content": f"Historical question {turn}"}
        )
        store.append_timeline(
            session_id,
            None,
            "assistant_message",
            {
                "content": f"Historical answer {turn}",
                "citation_source_ref_ids": [],
                "tool_calls": [],
            },
        )
    store.append_timeline(session_id, None, "user_message", {"content": "Current question"})

    context_rows, omitted_turns = store.model_context_timeline(session_id)
    context = ContextBuilder(store).build(session_id)

    assert len(store.timeline(session_id)) == 301
    assert len(context_rows) == 129
    assert omitted_turns == 86
    assert [message.content for message in context if message.role == "user"][-1] == (
        "Current question"
    )
    assert context_rows[0].kind == "user_message"
    assert any("older timeline turns: 86" in message.content for message in context)


@pytest.mark.anyio
async def test_registered_tools_are_progressively_exposed_on_initial_and_resumed_turns(
    store,
) -> None:  # type: ignore[no-untyped-def]
    result = _zabbix_result()

    def handler(call: ToolCall) -> ToolResult:
        return result.model_copy(update={"call_id": call.call_id, "tool_name": call.tool_name})

    builder = ToolRegistryBuilder()
    for definition in _all_definitions():
        builder.register(definition, handler)
    registry = builder.freeze()
    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="expand",
                        tool_name=EXPAND_TOOL_NAME,
                        arguments={"tool_names": ["zabbix.event.list"]},
                    ),
                )
            ),
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="zabbix-1",
                        tool_name="zabbix.event.list",
                        arguments={"target_ref": "zabbix"},
                    ),
                )
            ),
            ModelTurn(
                assistant=AssistantMessage(
                    content="Events. [[source:zabbix-events-prod]]",
                    citation_source_ref_ids=("zabbix-events-prod",),
                )
            ),
        ]
    )
    session_id = store.create_session()

    await runtime(store, backend, registry).submit(session_id, "List events with a source")

    assert len(backend.calls) == 3
    assert [definition.name for definition in backend.calls[0][1]] == [EXPAND_TOOL_NAME]
    assert [definition.name for definition in backend.calls[1][1]] == [
        EXPAND_TOOL_NAME,
        "zabbix.event.list",
    ]
    assert [definition.name for definition in backend.calls[2][1]] == [
        EXPAND_TOOL_NAME,
        "zabbix.event.list",
    ]
    assert _compact_provider_proxy(*backend.calls[1]) == EXPECTED_ZABBIX_EXPANSION_PROXY_BYTES
    assert _compact_provider_proxy(*backend.calls[2]) == EXPECTED_ZABBIX_RESUMED_PROXY_BYTES
    resumed = backend.calls[2][0]
    assistant_index = next(
        index
        for index, message in enumerate(resumed)
        if message.tool_calls and message.tool_calls[0].tool_name == "zabbix.event.list"
    )
    assert resumed[assistant_index + 1].role == "tool"
    assert resumed[assistant_index + 1].tool_call_id == "zabbix-1"
    assert len(store.timeline(session_id)[-2].payload["result"]["data"]["results"]) == 100


def test_incomplete_tool_pair_is_not_sent_to_provider(store) -> None:  # type: ignore[no-untyped-def]
    session_id = store.create_session()
    store.append_timeline(session_id, None, "user_message", {"content": "Old request"})
    store.append_timeline(
        session_id,
        None,
        "assistant_message",
        {
            "content": "",
            "citation_source_ref_ids": [],
            "tool_calls": [
                ModelToolCall(
                    call_id="missing-result",
                    tool_name="zabbix.event.list",
                    arguments={"target_ref": "zabbix"},
                ).model_dump(mode="json")
            ],
        },
    )
    store.append_timeline(session_id, None, "user_message", {"content": "Current request"})

    context = ContextBuilder(store).build(session_id)

    assert not any(message.tool_calls for message in context)
    assert [message.content for message in context if message.role == "user"] == [
        "Old request",
        "Current request",
    ]
    assert any("incomplete/unpaired blocks: 1" in message.content for message in context)
