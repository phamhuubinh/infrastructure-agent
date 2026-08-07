from __future__ import annotations

import warnings
from dataclasses import FrozenInstanceError

import pytest

from src.shared.execution.command_result import CommandResult, CommandStatus
from src.shared.execution.tool_result import ToolResult
from src.tool.capability_result import CapabilityResult, CapabilityStatus
from src.tool.errors import CapabilityErrorCode


def test_valid_and_valid_empty_are_distinct_successes() -> None:
    with pytest.deprecated_call(match="Unstructured capability payloads"):
        valid = CapabilityResult.from_legacy({"count": 1})
    with pytest.deprecated_call(match="Unstructured capability payloads"):
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

    with pytest.deprecated_call(match="Unstructured capability payloads"):
        result = CapabilityResult.from_legacy(
            {"count": 0, "items": []},
            command_results=(command,),
        )

    assert result.status is CapabilityStatus.COLLECTION_FAILED
    assert result.success is False
    assert result.data is None
    assert result.command_results == (command,)
    assert result.capability_error is not None
    assert result.capability_error.code is CapabilityErrorCode.NON_ZERO_EXIT


def test_mixed_command_outcomes_preserve_partial_data() -> None:
    commands = (
        CommandResult(status=CommandStatus.SUCCESS, stdout="valid"),
        CommandResult(status=CommandStatus.TIMEOUT, stderr="timeout"),
    )

    with pytest.deprecated_call(match="Unstructured capability payloads"):
        result = CapabilityResult.from_legacy(
            {"value": "valid"},
            command_results=commands,
        )

    assert result.status is CapabilityStatus.PARTIAL
    assert result.success is False
    assert result.data == {"value": "valid"}
    assert result.capability_error is not None
    assert result.capability_error.code is CapabilityErrorCode.TIMEOUT


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
    assert result.capability_error is capability.capability_error


def test_capability_result_is_immutable() -> None:
    result = CapabilityResult(status=CapabilityStatus.VALID)
    with pytest.raises(FrozenInstanceError):
        result.status = CapabilityStatus.PARTIAL  # type: ignore[misc]


def test_internal_legacy_bridge_can_avoid_duplicate_runtime_warning() -> None:
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        result = CapabilityResult.from_legacy({"count": 1}, warn_legacy=False)

    assert result.status is CapabilityStatus.VALID
    assert list(recorded) == []
