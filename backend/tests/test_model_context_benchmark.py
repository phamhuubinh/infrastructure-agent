from __future__ import annotations

import json

import pytest

from orion.benchmarks.model_context import (
    OFFLINE_BUDGETS,
    BenchmarkMeasurement,
    BenchmarkReport,
    benchmark_scenarios,
    provider_payload,
    run_offline_benchmark,
)
from orion.chat.context_builder import CONVERSATION_STATE_MAX_BYTES
from orion.contracts import ContextMessage
from orion.models.providers.openai_compatible import OpenAICompatibleBackend
from orion.tool_runtime.registry import EXPAND_TOOL_NAME


@pytest.mark.anyio
async def test_offline_model_context_benchmark_uses_canonical_runtime_shapes() -> None:
    report = await run_offline_benchmark()
    measurements = {item.scenario: item for item in report.measurements}

    assert [item.name for item in benchmark_scenarios()] == [
        "fresh_hello",
        "direct_non_tool",
        "project_fresh",
        "calculator_progressive",
        "ambiguous_infrastructure_initial",
        "ten_turn_ordinary",
        "checkpoint_trigger",
        "long_steady_state",
    ]
    assert all(item.status == "PASS" for item in report.measurements)
    assert measurements["fresh_hello"].payload_bytes <= OFFLINE_BUDGETS["fresh_payload_bytes"]
    assert measurements["fresh_hello"].catalog_bytes == 0
    progressive = measurements["progressive_exposure_projections"]
    assert progressive.catalog_bytes == 0
    assert progressive.metrics["expansion_schema_bytes"] > 0
    assert (
        progressive.metrics["one_expanded_payload_bytes"]
        <= OFFLINE_BUDGETS["one_expanded_payload_bytes"]
    )
    assert (
        progressive.metrics["three_expanded_payload_bytes"]
        <= OFFLINE_BUDGETS["three_expanded_payload_bytes"]
    )
    assert (
        measurements["ten_turn_ordinary"].payload_bytes <= OFFLINE_BUDGETS["ten_turn_payload_bytes"]
    )
    assert (
        measurements["long_steady_state"].payload_bytes
        <= OFFLINE_BUDGETS["long_steady_payload_bytes"]
    )
    checkpoint = measurements["checkpoint_trigger"]
    assert checkpoint.metrics["summary_payload_bytes"] <= OFFLINE_BUDGETS["summary_payload_bytes"]
    assert checkpoint.metrics["summary_state_bytes"] <= CONVERSATION_STATE_MAX_BYTES
    assert checkpoint.summary_calls == 1
    assert checkpoint.main_calls == 1
    assert checkpoint.visible_tools_by_call[0] == ()
    assert checkpoint.metrics["summary_omits_tools"] is True
    assert measurements["long_steady_state"].summary_calls == 0
    assert measurements["long_steady_state"].main_calls == 1

    calculator = measurements["calculator_progressive"]
    assert calculator.main_calls == 3
    assert calculator.visible_tools_by_call == (
        (EXPAND_TOOL_NAME,),
        (EXPAND_TOOL_NAME, "calculator.evaluate"),
        (EXPAND_TOOL_NAME, "calculator.evaluate"),
    )
    assert measurements["progressive_exposure_reset"].visible_tools_by_call == (
        (EXPAND_TOOL_NAME,),
    )
    ambiguous = measurements["ambiguous_infrastructure_initial"]
    assert ambiguous.visible_tools_by_call == ((EXPAND_TOOL_NAME,),)
    assert ambiguous.metrics["infrastructure_operations_executed"] == 0
    assert measurements["project_fresh"].metrics["uses_project_context"] is True
    assert measurements["empty_tools_provider_representation"].metrics["tools_key_omitted"] is True


@pytest.mark.anyio
async def test_benchmark_report_is_stable_text_and_valid_json() -> None:
    report = await run_offline_benchmark()

    assert report.to_text() == report.to_text()
    parsed = json.loads(report.to_json())
    assert parsed["mode"] == "offline"
    assert [item["scenario"] for item in parsed["measurements"]] == [
        measurement.scenario for measurement in report.measurements
    ]
    assert "fresh_hello" in report.to_text()


@pytest.mark.anyio
async def test_offline_benchmark_never_delegates_to_the_network_provider(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def network_forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("offline benchmark attempted a provider request")

    monkeypatch.setattr(OpenAICompatibleBackend, "stream", network_forbidden)

    report = await run_offline_benchmark()

    assert report.mode == "offline"


def test_empty_tools_provider_projection_omits_tools_key() -> None:
    payload = provider_payload((ContextMessage(role="user", content="summary"),), ())

    assert "tools" not in payload


def test_budget_failure_names_the_scenario_measurement_budget_and_reference() -> None:
    report = BenchmarkReport(
        "offline",
        (
            BenchmarkMeasurement(
                scenario="fresh_hello",
                payload_bytes=2_001,
                catalog_bytes=None,
                message_count=1,
                main_calls=1,
                summary_calls=0,
                visible_tools_by_call=(),
                returned_tool_calls_by_call=(),
                input_tokens_by_call=(),
                output_tokens_by_call=(),
                budgets={"payload_bytes": 2_000},
            ),
        ),
    )

    with pytest.raises(
        AssertionError,
        match=r"fresh_hello payload_bytes grew to 2001; budget: 2000; previous reference: 1680",
    ):
        report.require_passing()
