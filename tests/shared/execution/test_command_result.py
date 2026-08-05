from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from src.shared.execution.command_result import CommandResult, CommandStatus


def test_command_result_retains_transport_fields() -> None:
    result = CommandResult(
        status=CommandStatus.NON_ZERO_EXIT,
        exit_code=7,
        stdout="partial output",
        stderr="failure detail",
        error_type="NonZeroExit",
        command_id="cmd-1",
        target="monitor",
        duration_ms=12,
    )

    assert result.status is CommandStatus.NON_ZERO_EXIT
    assert result.exit_code == 7
    assert result.stdout == "partial output"
    assert result.stderr == "failure detail"
    assert result.success is False


def test_success_and_empty_success_are_successful() -> None:
    assert CommandResult(status=CommandStatus.SUCCESS).success is True
    assert CommandResult(status=CommandStatus.EMPTY_SUCCESS).success is True
    assert CommandResult(status=CommandStatus.TIMEOUT).success is False


def test_legacy_tuple_adapter() -> None:
    ok, output = CommandResult(
        status=CommandStatus.NON_ZERO_EXIT,
        stderr="remote error",
        target="monitor",
    )

    assert ok is False
    assert output == "remote error"


def test_command_result_is_immutable() -> None:
    result = CommandResult(status=CommandStatus.SUCCESS)
    with pytest.raises(FrozenInstanceError):
        result.status = CommandStatus.TIMEOUT  # type: ignore[misc]


def test_repr_omits_stream_content_and_serialization_redacts_credentials() -> None:
    result = CommandResult(
        status=CommandStatus.NON_ZERO_EXIT,
        stdout="token=super-secret",
        stderr="Authorization: Bearer abc123 password=hunter2",
        target="ssh://root:secret@monitor",
    )

    rendered = repr(result)
    serialized = result.to_dict()
    combined = f"{rendered} {serialized}"

    assert "super-secret" not in combined
    assert "abc123" not in combined
    assert "hunter2" not in combined
    assert "root:secret" not in combined
    assert serialized["stdout"] == "token=<redacted>"
