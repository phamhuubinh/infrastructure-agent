"""Offline regressions derived from the DIAG-03 three-row projection cliff."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from conftest import ScriptedBackend, runtime

from orion.chat.context_builder import MAX_CONVERSATION_BYTES, ContextBuilder, _messages_bytes
from orion.chat.diagnostics import model_input_snapshot
from orion.chat.model_context import compact_json, project_tool_result
from orion.contracts import (
    AssistantMessage,
    ModelToolCall,
    ModelTurn,
    ReadProgress,
    SourceRef,
    ToolDefinition,
    ToolResult,
)
from orion.tool_runtime.registry import EXPAND_TOOL_NAME, ToolRegistryBuilder

GROUNDING_RULE = (
    "_orion_projection: source_data_state=upstream_nonempty_omitted/partial, partial/omitted "
    "data_state or essential_metadata, omitted_items>0 or omitted keys mean incomplete evidence, "
    "not absence/zero/no activity/incident/anomaly. Disclose coverage limits or seek authorized "
    "evidence as appropriate. source_data_state=upstream_empty supports emptiness only within "
    "query scope/time/limit."
)


def three_row_result() -> ToolResult:
    # Same nested result/envelope shape as DIAG-03, with synthetic identities/text.
    result = ToolResult(
        call_id="chatcmpl-tool-0000000000000000",
        tool_name="sample.record.get",
        status="success",
        data={
            "target_ref": "sample",
            "results": [
                {
                    "trigger_id": str(10000 + i),
                    "description": "Observed condition " + str(i),
                    "severity": "average",
                    "state": "problem",
                }
                for i in range(3)
            ],
        },
        sources=(
            SourceRef(
                source_ref_id="00000000-0000-5000-8000-000000000000",
                source_kind="sample",
                source_id="sample",
                section="get",
                label="sample",
                retrieved_at=datetime(2026, 9, 10, 11, 40, 6, 506033, tzinfo=UTC),
            ),
        ),
        read_progress=ReadProgress(
            observation_id="sample:sample:get",
            certainty="confirmed",
            coverage={"target_ref": "sample", "only_problem": True, "limit": 200},
        ),
    )
    # Pad a row that may be omitted, not the immutable envelope.
    result.data["results"][2]["description"] += "x" * (995 - len(canonical(result).encode()))
    assert len(canonical(result).encode()) == 995
    return result


def canonical(result: ToolResult) -> str:
    value = result.model_dump(mode="json")
    if value["read_progress"] is None:
        del value["read_progress"]
    return compact_json(value)


def live_shaped_event_result() -> ToolResult:
    """Synthetic structural equivalent of the three-event live projection failure."""
    return ToolResult(
        call_id="live-shape",
        tool_name="zabbix.event.list",
        status="success",
        data={
            "target_ref": "zabbix",
            "results": [
                {"event_id": str(index), "severity": "high", "detail": "é漢字" * 100}
                for index in range(3)
            ],
            "time_coverage": {
                "returned_count": 3,
                "zero_matches_in_query": False,
                "absence_of_events_established": False,
                "possibly_truncated": False,
                "result_completeness": "unknown",
                "from": "2026-09-01T00:00:00Z",
                "to": "2026-09-02T00:00:00Z",
            },
            "evidence_scope": {"kind": "bounded", "limitations": ["x" * 300]},
        },
    )


def test_995_byte_nested_result_keeps_useful_rows_at_994() -> None:
    result = three_row_result()
    before = result.model_dump(mode="json")
    assert project_tool_result(result, 995) == canonical(result)
    encoded = project_tool_result(result, 994)
    projected = json.loads(encoded)
    assert len(encoded.encode()) <= 994
    rows = (projected["data"] or {}).get("results", [])
    assert rows and rows[0]["trigger_id"] == "10000"
    coverage = next(
        item
        for item in projected["_orion_projection"]["omissions"]
        if item["path"] == "$.data.results"
    )
    assert coverage["original_items"] == 3
    assert coverage["included_items"] == len(rows)
    assert coverage["omitted_items"] == 3 - len(rows)
    assert result.model_dump(mode="json") == before


def test_nonempty_events_remain_unambiguous_when_rows_and_coverage_are_omitted() -> None:
    result = live_shaped_event_result()
    before = result.model_dump(mode="json")
    cap = 465
    encoded = project_tool_result(result, cap)
    projected = json.loads(encoded)
    metadata = projected["_orion_projection"]

    assert len(encoded.encode("utf-8")) == cap
    assert projected["data"] is None
    assert metadata["data_state"] == "omitted"
    assert metadata["source_data_state"] == "upstream_nonempty_omitted"
    assert metadata["essential_metadata"] == {
        "evidence_scope": "omitted",
        "time_coverage": "omitted",
    }
    assert metadata["unreported_list_items"] == {
        "original_items": 4,
        "included_items": 0,
        "omitted_items": 4,
    }
    # This aggregate includes the nested limitations list as well as events;
    # it is not an event/observation count.
    assert metadata["unreported_list_items"]["original_items"] != 3
    assert result.model_dump(mode="json") == before

    larger = json.loads(project_tool_result(result, 500))
    assert len(project_tool_result(result, 500).encode("utf-8")) <= 500
    assert larger["_orion_projection"]["source_data_state"] == "upstream_nonempty_partial"
    assert larger["data"]["time_coverage"]["returned_count"] == 3
    assert larger["data"]["time_coverage"].get("absence_of_events_established") is not True

    absence_critical = json.loads(project_tool_result(result, 600))
    assert absence_critical["data"]["time_coverage"]["absence_of_events_established"] is False
    row_counts = []
    for budget in (cap, 500, 600, 1_200, 3_000):
        value = json.loads(project_tool_result(result, budget))
        assert len(project_tool_result(result, budget).encode("utf-8")) <= budget
        row_counts.append(len((value["data"] or {}).get("results", [])))
    assert row_counts == sorted(row_counts)

    empty = ToolResult(call_id="empty", tool_name=result.tool_name, status="success", data=[])
    upstream_empty = json.loads(project_tool_result(empty, cap))
    assert upstream_empty["data"] == []
    assert upstream_empty != projected


@pytest.mark.parametrize("offset", range(-16, 5))
def test_threshold_sweep_is_deterministic_and_monotonic(offset: int) -> None:
    result = three_row_result()
    cap = 995 + offset
    counts = []
    states = {"omitted": 0, "partial": 1, "complete": 2}
    ranks = []
    for budget in [cap, cap + 1]:
        encoded = project_tool_result(result, budget)
        assert encoded == project_tool_result(result, budget)
        assert len(encoded.encode()) <= budget
        value = json.loads(encoded)
        counts.append(len((value["data"] or {}).get("results", [])))
        ranks.append(states[value.get("_orion_projection", {}).get("data_state", "complete")])
    assert counts[0] <= counts[1]
    assert 3 - counts[0] >= 3 - counts[1]
    assert ranks[0] <= ranks[1]


def _list_counts(value, path="$.data"):  # type: ignore[no-untyped-def]
    counts = {}
    if isinstance(value, list):
        counts[path] = len(value)
        for index, item in enumerate(value):
            counts.update(_list_counts(item, f"{path}[{index}]"))
    elif isinstance(value, dict):
        for key, item in value.items():
            counts.update(_list_counts(item, f"{path}.{key}"))
    return counts


@pytest.mark.parametrize(
    "data",
    [
        [{"id": i, "text": 'é漢字🙂\\"' * 20} for i in range(3)],
        {"outer": {"inner": [{"id": i, "text": "x" * 90} for i in range(3)]}},
        {
            "first": [{"id": i} for i in range(10)],
            "second": [{"id": i, "detail": "x" * 80} for i in range(5)],
            "large": "y" * 200,
        },
        {"rows": [{"nested": [1, 2, 3], "text": "x" * 100} for _ in range(3)]},
        {
            "evidence_scope": {"kind": "bounded", "limitations": ["x" * 80]},
            "time_coverage": {"from": "yesterday", "to": "today", "limit": 3},
            "rows": [{"id": i, "detail": "x" * 200} for i in range(3)],
        },
    ],
)
def test_structured_budget_sweeps_preserve_cardinality_envelope_and_bytes(data) -> None:  # type: ignore[no-untyped-def]
    result = ToolResult(call_id="sweep", tool_name="arbitrary.read", status="success", data=data)
    before = result.model_dump(mode="json")
    original_counts = _list_counts(data)
    previous = dict.fromkeys(original_counts, 0)
    previous_rank = 0
    original_bytes = len(canonical(result).encode())
    for cap in sorted(
        {*range(200, original_bytes + 20, 13), *range(original_bytes - 16, original_bytes + 5)}
    ):
        encoded = project_tool_result(result, cap)
        assert encoded == project_tool_result(result, cap)
        value = json.loads(encoded)
        assert value["call_id"] == result.call_id
        assert value["status"] == result.status
        assert value["error"] is None and value["sources"] == []
        counts = _list_counts(value["data"])
        for path, total in original_counts.items():
            included = counts.get(path, 0)
            assert previous[path] <= included <= total, (cap, path, previous, counts)
            previous[path] = included
        metadata = value.get("_orion_projection", {})
        rank = {"omitted": 0, "partial": 1, "complete": 2}[metadata.get("data_state", "complete")]
        assert previous_rank <= rank
        previous_rank = rank
        if len(encoded.encode()) > cap:
            # Only the data-free immutable envelope + truthful summary may overflow.
            assert value["data"] is None and metadata["data_state"] == "omitted"
        for record in metadata.get("omissions", []):
            if "original_items" in record:
                assert record["original_items"] == original_counts[record["path"]]
                assert record["included_items"] == counts.get(record["path"], 0)
                assert (
                    record["omitted_items"] == record["original_items"] - record["included_items"]
                )
        if cap >= original_bytes:
            assert encoded == canonical(result)
        assert result.model_dump(mode="json") == before


@pytest.mark.parametrize("nested", [False, True])
def test_upstream_empty_and_omitted_positive_are_not_interchangeable(nested: bool) -> None:
    def result(rows):  # type: ignore[no-untyped-def]
        return ToolResult(
            call_id="empty",
            tool_name="arbitrary.read",
            status="success",
            data={"nested": {"rows": rows}} if nested else rows,
        )

    empty = result([])
    positive = result([{"id": i, "text": "x" * 100} for i in range(3)])
    assert json.loads(project_tool_result(empty, 1000))["data"] == empty.data
    omitted = json.loads(project_tool_result(positive, 1))
    assert omitted["data"] is None
    metadata = omitted["_orion_projection"]
    assert metadata["data_state"] == "omitted"
    assert metadata["unreported_list_items"] == {
        "original_items": 3,
        "included_items": 0,
        "omitted_items": 3,
    }
    if not nested:
        upstream = json.loads(project_tool_result(empty, 1))
        assert upstream["data"] == []
        assert upstream["_orion_projection"]["data_state"] == "upstream_empty"
        assert upstream["_orion_projection"]["source_data_state"] == "upstream_empty"
    else:
        upstream = json.loads(project_tool_result(empty, 330))
        assert upstream["data"] != omitted["data"]


def test_exact_error_source_progress_envelope_survives_irreducible_cap() -> None:
    original = three_row_result()
    failed = ToolResult.failure(original.call_id, original.tool_name, "upstream_error", "x" * 900)
    failed = failed.model_copy(
        update={
            "sources": original.sources,
            "read_progress": original.read_progress,
            "data": original.data,
        }
    )
    before = failed.model_dump(mode="json")
    value = json.loads(project_tool_result(failed, 50))
    assert {key: value[key] for key in before if key != "data"} == {
        key: val for key, val in before.items() if key != "data"
    }
    assert value["data"] is None
    assert value["_orion_projection"]["data_state"] == "omitted"
    assert failed.model_dump(mode="json") == before


def test_essential_metadata_states_match_actual_projection() -> None:
    data = {
        "evidence_scope": {"kind": "bounded", "limitations": ["x" * 900]},
        "time_coverage": {"from": "2026-01-01", "to": "2026-01-02"},
        "results": [{"id": i, "detail": "x" * 500} for i in range(20)],
    }
    result = ToolResult(call_id="scope", tool_name="arbitrary.read", status="success", data=data)
    seen = set()
    for cap in [1, 400, 600, 1000, 1800, 2400]:
        value = json.loads(project_tool_result(result, cap))
        for key, state in value["_orion_projection"]["essential_metadata"].items():
            actual = (value["data"] or {}).get(key)
            assert state == (
                "omitted" if actual is None else "complete" if actual == data[key] else "partial"
            )
            seen.add(state)
        if cap >= 1800:
            assert value["data"]["evidence_scope"] == data["evidence_scope"]
            assert value["data"]["time_coverage"] == data["time_coverage"]
    assert seen == {"complete", "partial", "omitted"}


def test_bounded_omission_records_keep_unreported_cardinality() -> None:
    result = ToolResult(
        call_id="many",
        tool_name="arbitrary.read",
        status="success",
        data={
            f"collection_{i}": [{"id": j, "text": "x" * 1000} for j in range(5)] for i in range(30)
        },
    )
    encoded = project_tool_result(result, 1500)
    value = json.loads(encoded)
    metadata = value["_orion_projection"]
    assert len(encoded.encode()) <= 1500
    assert len(metadata["omissions"]) <= 12
    assert metadata["omission_entries_omitted"] > 0
    records = [item for item in metadata["omissions"] if "original_items" in item]
    aggregate = metadata["unreported_list_items"]
    included = sum(_list_counts(value["data"]).values())
    assert sum(item["original_items"] for item in records) + aggregate["original_items"] == 150
    assert sum(item["included_items"] for item in records) + aggregate["included_items"] == included
    assert (
        sum(item["omitted_items"] for item in records) + aggregate["omitted_items"]
        == 150 - included
    )


@pytest.mark.anyio
@pytest.mark.parametrize("empty", [False, True])
async def test_backend_receives_grounding_rule_projection_and_current_prompt(store, empty) -> None:  # type: ignore[no-untyped-def]
    source = SourceRef(
        source_ref_id="fixture-source",
        source_kind="internet",
        source_id="fixture",
        url="https://example.invalid/offline",
    )
    result = ToolResult(
        call_id="read",
        tool_name="arbitrary.read",
        status="success",
        data=[] if empty else [{"id": i, "text": "é漢字🙂" * 40} for i in range(60)],
        sources=(source,),
    )
    before = result.model_dump(mode="json")
    registry = ToolRegistryBuilder()
    registry.register(
        ToolDefinition(
            name=result.tool_name,
            handler_key=result.tool_name,
            description="Offline fixture.",
            input_schema={"type": "object", "properties": {}},
        ),
        lambda call: result,
    )
    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="expand",
                        tool_name=EXPAND_TOOL_NAME,
                        arguments={"tool_names": [result.tool_name]},
                    ),
                )
            ),
            ModelTurn(
                tool_calls=(
                    ModelToolCall(call_id=result.call_id, tool_name=result.tool_name, arguments={}),
                )
            ),
            ModelTurn(
                assistant=AssistantMessage(
                    content="Scoped evidence. [[source:fixture-source]]",
                    citation_source_ref_ids=(source.source_ref_id,),
                )
            ),
        ]
    )
    session = store.create_session()
    prompt = "Explain the observations with coverage limitations and a source."
    outcome = await runtime(store, backend, registry.freeze()).submit(session, prompt)
    messages = backend.calls[-1][0]
    assert len(backend.calls) == 3 and outcome.status == "completed"
    assert messages[0].role == "system" and messages[0].content.endswith(GROUNDING_RULE)
    assert ContextBuilder(store).build(session)[0] == messages[0]
    assert [message.content for message in messages if message.role == "user"] == [prompt]
    assert all(_messages_bytes(call[0]) <= MAX_CONVERSATION_BYTES for call in backend.calls)
    tool = next(message for message in messages if message.tool_call_id == result.call_id)
    value = json.loads(tool.content)
    if empty:
        assert tool.content == canonical(result) and value["data"] == []
    else:
        metadata = value["_orion_projection"]
        assert metadata["data_state"] == "partial"
        assert tool.content == project_tool_result(result, metadata["maximum_bytes"])
        assert len(tool.content.encode()) <= metadata["maximum_bytes"] <= 6000
        coverage = next(item for item in metadata["omissions"] if item["path"] == "$.data")
        assert 0 < coverage["included_items"] < 60
        assert coverage["omitted_items"] == 60 - len(value["data"])
        snapshot = model_input_snapshot(messages, (), (source.source_ref_id,), 0)
        captured = next(
            item
            for item in snapshot["tool_result_projections"]
            if item["tool_call_id"] == result.call_id
        )
        assert captured["content"] == tool.content
        assert captured["projection_omissions"] == metadata["omissions"]
    assert value["sources"] == [source.model_dump(mode="json")]
    persisted = next(
        item.payload["result"]
        for item in store.timeline(session)
        if item.kind == "tool_result" and item.call_id == result.call_id
    )
    assert persisted == before == result.model_dump(mode="json")
