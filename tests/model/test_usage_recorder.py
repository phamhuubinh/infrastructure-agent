from __future__ import annotations

from src.model.usage_metadata import ModelCallUsage
from src.model.usage_recorder import MAX_RECORDED_CALLS, ModelUsageRecorder


def test_aggregates_counts_latency_and_tokens_by_purpose() -> None:
    recorder = ModelUsageRecorder()
    recorder.record(
        ModelCallUsage(
            input_tokens=10,
            reasoning_tokens=4,
            visible_output_tokens=6,
            total_output_tokens=10,
            purpose="planner",
            latency_ms=12.5,
        )
    )
    recorder.record(
        ModelCallUsage(
            input_tokens=30,
            reasoning_tokens=None,
            visible_output_tokens=25,
            total_output_tokens=25,
            purpose="relevance",
            latency_ms=3.0,
        )
    )
    recorder.record(
        ModelCallUsage(
            input_tokens=None,
            reasoning_tokens=None,
            visible_output_tokens=None,
            total_output_tokens=None,
            purpose="relevance",
            latency_ms=None,
        )
    )

    trace = recorder.to_trace_dict()

    assert trace["calls"] == 3
    assert trace["dropped_calls"] == 0
    assert trace["by_purpose"]["planner"] == {
        "calls": 1,
        "latency_ms": 12.5,
        "input_tokens": 10,
        "reasoning_tokens": 4,
        "visible_output_tokens": 6,
        "total_output_tokens": 10,
    }
    assert trace["by_purpose"]["relevance"] == {
        "calls": 2,
        "latency_ms": 3.0,
        "input_tokens": 30,
        "reasoning_tokens": None,
        "visible_output_tokens": 25,
        "total_output_tokens": 25,
    }
    assert len(trace["per_call"]) == 3
    assert trace["per_call"][2]["input_tokens"] is None


def test_unknown_purpose_buckets_under_unknown() -> None:
    recorder = ModelUsageRecorder()
    recorder.record(ModelCallUsage(input_tokens=5))

    trace = recorder.to_trace_dict()

    assert trace["by_purpose"]["unknown"] == {
        "calls": 1,
        "latency_ms": None,
        "input_tokens": 5,
        "reasoning_tokens": None,
        "visible_output_tokens": None,
        "total_output_tokens": None,
    }


def test_per_call_entries_are_bounded() -> None:
    recorder = ModelUsageRecorder()
    for _ in range(MAX_RECORDED_CALLS + 3):
        recorder.record(ModelCallUsage(input_tokens=1, purpose="relevance"))

    trace = recorder.to_trace_dict()

    assert trace["calls"] == MAX_RECORDED_CALLS + 3
    assert len(trace["per_call"]) == MAX_RECORDED_CALLS
    assert trace["dropped_calls"] == 3
    assert trace["by_purpose"]["relevance"]["calls"] == MAX_RECORDED_CALLS + 3
    assert trace["by_purpose"]["relevance"]["input_tokens"] == MAX_RECORDED_CALLS + 3


def test_record_mapping_normalizes_openai_and_anthropic_shapes() -> None:
    recorder = ModelUsageRecorder()
    recorder.record_mapping(
        {
            "prompt_tokens": 11,
            "completion_tokens": 12,
            "completion_tokens_details": {"reasoning_tokens": 3},
        },
        purpose="planner",
        provider="test",
        model="semantic-test",
        latency_ms=4.0,
    )
    recorder.record_mapping(
        {"input_tokens": 7, "output_tokens": 9},
        purpose="response",
        provider="anthropic",
    )

    by_purpose = recorder.to_trace_dict()["by_purpose"]

    assert by_purpose["planner"] == {
        "calls": 1,
        "latency_ms": 4.0,
        "input_tokens": 11,
        "reasoning_tokens": 3,
        "visible_output_tokens": 9,
        "total_output_tokens": 12,
    }
    assert by_purpose["response"]["input_tokens"] == 7
    assert by_purpose["response"]["total_output_tokens"] == 9
    assert by_purpose["response"]["visible_output_tokens"] == 9
    assert by_purpose["response"]["reasoning_tokens"] is None


def test_record_mapping_ignores_unrecognized_payloads() -> None:
    recorder = ModelUsageRecorder()
    recorder.record_mapping(
        None,
        purpose="planner",
        provider="test",
        model="m",
    )

    trace = recorder.to_trace_dict()

    assert trace["by_purpose"]["planner"]["input_tokens"] is None
    assert trace["by_purpose"]["planner"]["calls"] == 1


def test_reset_clears_all_calls() -> None:
    recorder = ModelUsageRecorder()
    recorder.record(ModelCallUsage(input_tokens=1))

    recorder.reset()

    trace = recorder.to_trace_dict()
    assert trace["calls"] == 0
    assert trace["by_purpose"] == {}
    assert trace["per_call"] == []
