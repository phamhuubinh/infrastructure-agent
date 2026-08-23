from __future__ import annotations

import json

from src.pipeline.execution_trace import (
    ExecutionTrace,
    LLMUsageReason,
    StageStatus,
    StageTrace,
)


def test_trace_ids_are_unique() -> None:
    first = ExecutionTrace(
        user_request="one"
    )
    second = ExecutionTrace(
        user_request="two"
    )

    assert first.trace_id != second.trace_id


def test_stage_default_is_pending() -> None:
    stage = StageTrace(
        name="execute"
    )

    assert stage.status is (
        StageStatus.PENDING
    )
    assert stage.confidence is None


def test_trace_serialization_is_json_safe() -> None:
    trace = ExecutionTrace(
        user_request="check cpu",
        stages={
            "execute": StageTrace(
                name="execute",
                status=(
                    StageStatus.SUCCEEDED
                ),
                planned_capabilities=[
                    "system.cpu"
                ],
            )
        },
        llm_usage_reason=(
            LLMUsageReason.NONE
        ),
    )

    payload = trace.to_dict()

    json.dumps(payload)

    assert payload["user_request"] == (
        "check cpu"
    )
    assert (
        payload["stages"]["execute"]
        ["status"]
        == "SUCCEEDED"
    )


def test_trace_serialization_does_not_invent_raw_evidence() -> None:
    trace = ExecutionTrace(
        stages={
            "execute": StageTrace(
                name="execute",
                evidence_names=["CPU"],
            )
        }
    )

    raw = json.dumps(
        trace.to_dict()
    )

    assert "CPU" in raw
    assert "raw_data" not in raw
