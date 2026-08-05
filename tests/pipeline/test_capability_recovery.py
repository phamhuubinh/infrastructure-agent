from __future__ import annotations

from src.pipeline.capability_recovery import (
    CapabilityRecovery,
    CapabilityRecoverySpec,
    RecoveryStopReason,
)
from src.shared.execution.tool_result import ToolResult
from src.tool.capability_result import CapabilityStatus
from src.tool.errors import (
    CapabilityError,
    CapabilityErrorCategory,
    CapabilityErrorCode,
)


def _failure(
    code: CapabilityErrorCode, category: CapabilityErrorCategory
) -> ToolResult:
    return ToolResult(
        success=False,
        error=code.value,
        capability_status=CapabilityStatus.COLLECTION_FAILED,
        capability_error=CapabilityError(code, category, code.value, False),
    )


def test_declared_environment_alternative_recovers_once() -> None:
    recovery = CapabilityRecovery(
        {
            "primary": CapabilityRecoverySpec(
                "primary", ("fallback",), ("command_not_found",)
            )
        }
    )
    calls: list[str] = []

    outcome = recovery.recover(
        "primary",
        _failure(
            CapabilityErrorCode.COMMAND_NOT_FOUND,
            CapabilityErrorCategory.ENVIRONMENT,
        ),
        lambda name: calls.append(name)
        or ToolResult(
            success=True,
            data={"value": 1},
            produced_fact_names=("cpu.usage",),
        ),
    )

    assert outcome.recovered
    assert outcome.recovered_by == "fallback"
    assert calls == ["fallback"]
    assert outcome.attempts[0].facts_recovered == ("cpu.usage",)


def test_transport_timeout_never_launches_more_remote_commands() -> None:
    recovery = CapabilityRecovery(
        {
            "primary": CapabilityRecoverySpec(
                "primary", ("fallback",), ("timeout",)
            )
        }
    )
    calls: list[str] = []

    outcome = recovery.recover(
        "primary",
        _failure(CapabilityErrorCode.TIMEOUT, CapabilityErrorCategory.TRANSPORT),
        lambda name: calls.append(name) or ToolResult(success=True),
    )

    assert calls == []
    assert outcome.stop_reason is RecoveryStopReason.TRANSPORT_FAILURE


def test_recovery_tries_declared_alternatives_without_looping_past_depth_two() -> None:
    recovery = CapabilityRecovery(
        {
            "primary": CapabilityRecoverySpec(
                "primary", ("fallback-a", "fallback-b", "fallback-c"),
                ("command_not_found",),
            )
        },
        max_depth=2,
    )
    calls: list[str] = []

    outcome = recovery.recover(
        "primary",
        _failure(
            CapabilityErrorCode.COMMAND_NOT_FOUND,
            CapabilityErrorCategory.ENVIRONMENT,
        ),
        lambda name: calls.append(name)
        or _failure(
            CapabilityErrorCode.COMMAND_NOT_FOUND,
            CapabilityErrorCategory.ENVIRONMENT,
        ),
    )

    assert calls == ["fallback-a", "fallback-b"]
    assert len(outcome.attempts) == 2
    assert outcome.stop_reason is RecoveryStopReason.MAX_DEPTH
