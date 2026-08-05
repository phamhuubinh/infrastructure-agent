from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from src.shared.execution.command_result import CommandResult, CommandStatus
from src.shared.execution.tool_result import ToolResult
from src.tool.capability_result import CapabilityResult, CapabilityStatus


def test_valid_and_valid_empty_are_distinct_successes() -> None:
    valid = CapabilityResult.from_legacy({"count": 1})
    empty = CapabilityResult.from_legacy([])

    assert valid.status is CapabilityStatus.VALID
    assert empty.status is CapabilityStatus.VALID_EMPTY
    assert valid.success is True
    assert empty.success is True


def test_failed_command_cannot_be_wrapped_as_success() -> None:
    command = CommandResult(
        status=CommandStatus.NON_ZERO_EXIT,
        exit_code=1,
        stderr="failed",
    )

    result = CapabilityResult.from_legacy(
        {"count": 0, "items": []},
        command_results=(command,),
    )

    assert result.status is CapabilityStatus.COLLECTION_FAILED
    assert result.success is False
    assert result.data is None
    assert result.command_results == (command,)


def test_mixed_command_outcomes_preserve_partial_data() -> None:
    commands = (
        CommandResult(status=CommandStatus.SUCCESS, stdout="valid"),
        CommandResult(status=CommandStatus.TIMEOUT, stderr="timeout"),
    )

    result = CapabilityResult.from_legacy(
        {"value": "valid"},
        command_results=commands,
    )

    assert result.status is CapabilityStatus.PARTIAL
    assert result.success is False
    assert result.data == {"value": "valid"}


def test_tool_result_maps_capability_status_without_losing_commands() -> None:
    command = CommandResult(status=CommandStatus.COMMAND_NOT_FOUND)
    capability = CapabilityResult(
        status=CapabilityStatus.UNSUPPORTED,
        command_results=(command,),
        error="unsupported",
    )

    result = ToolResult.from_capability_result(capability)

    assert result.success is False
    assert result.capability_status is CapabilityStatus.UNSUPPORTED
    assert result.command_results == (command,)
    assert result.error == "unsupported"


def test_capability_result_is_immutable() -> None:
    result = CapabilityResult(status=CapabilityStatus.VALID)
    with pytest.raises(FrozenInstanceError):
        result.status = CapabilityStatus.PARTIAL  # type: ignore[misc]
