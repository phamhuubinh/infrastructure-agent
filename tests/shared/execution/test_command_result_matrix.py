"""DR1-801 — Unit test matrix cho CommandResult.

Bao phủ ma trận target local/SSH x toàn bộ CommandStatus để khoá lại
semantics của `success` và `legacy_output` (adapter tương thích ngược),
tránh regression âm thầm khi có người sửa `command_result.py`.
"""

from __future__ import annotations

import pytest

from src.shared.execution.command_result import CommandResult, CommandStatus

LOCAL_TARGET = "localhost"
SSH_TARGET = "monitor"

# status -> success kỳ vọng
_SUCCESS_STATUSES = {CommandStatus.SUCCESS, CommandStatus.EMPTY_SUCCESS}
_ALL_STATUSES = tuple(CommandStatus)


@pytest.mark.parametrize("target", [LOCAL_TARGET, SSH_TARGET])
@pytest.mark.parametrize("status", _ALL_STATUSES)
def test_success_flag_depends_only_on_status(
    status: CommandStatus, target: str
) -> None:
    """`success` phải nhất quán bất kể target, chỉ phụ thuộc status."""

    result = CommandResult(status=status, target=target)

    assert result.success is (status in _SUCCESS_STATUSES)


@pytest.mark.parametrize("target", [LOCAL_TARGET, SSH_TARGET])
@pytest.mark.parametrize("status", _ALL_STATUSES)
def test_legacy_output_never_raises_and_is_string(
    status: CommandStatus, target: str
) -> None:
    """Adapter cũ phải luôn trả về str hợp lệ, không None/exception."""

    result = CommandResult(
        status=status,
        target=target,
        stdout="stdout-data",
        stderr="stderr-data",
    )

    assert isinstance(result.legacy_output, str)


@pytest.mark.parametrize("target", [LOCAL_TARGET, SSH_TARGET])
def test_success_statuses_return_stdout_as_legacy_output(target: str) -> None:
    for status in _SUCCESS_STATUSES:
        result = CommandResult(
            status=status,
            target=target,
            stdout="stdout-data",
            stderr="stderr-data",
        )
        assert result.legacy_output == "stdout-data"


def test_command_not_found_on_localhost_suppresses_output() -> None:
    """Local COMMAND_NOT_FOUND không được rò rỉ stderr ra legacy_output."""

    result = CommandResult(
        status=CommandStatus.COMMAND_NOT_FOUND,
        target=LOCAL_TARGET,
        stderr="bash: foo: command not found",
    )
    assert result.legacy_output == ""


def test_command_not_found_via_file_not_found_error_suppresses_output() -> None:
    result = CommandResult(
        status=CommandStatus.COMMAND_NOT_FOUND,
        target=SSH_TARGET,
        error_type="FileNotFoundError",
        stderr="no such file",
    )
    assert result.legacy_output == ""


def test_command_not_found_on_remote_surfaces_stderr() -> None:
    """Remote COMMAND_NOT_FOUND (không phải FileNotFoundError) phải lộ diện."""

    result = CommandResult(
        status=CommandStatus.COMMAND_NOT_FOUND,
        target=SSH_TARGET,
        stderr="bash: foo: command not found",
    )
    assert result.legacy_output == "bash: foo: command not found"


@pytest.mark.parametrize("target", [LOCAL_TARGET, SSH_TARGET])
@pytest.mark.parametrize(
    "status", [CommandStatus.TIMEOUT, CommandStatus.UNSUPPORTED_ENVIRONMENT]
)
def test_timeout_and_unsupported_always_suppress_output(
    status: CommandStatus, target: str
) -> None:
    result = CommandResult(status=status, target=target, stderr="should not leak")
    assert result.legacy_output == ""


def test_non_zero_exit_on_localhost_suppresses_output() -> None:
    result = CommandResult(
        status=CommandStatus.NON_ZERO_EXIT,
        target=LOCAL_TARGET,
        stderr="local failure detail",
    )
    assert result.legacy_output == ""


def test_non_zero_exit_on_remote_surfaces_stderr() -> None:
    result = CommandResult(
        status=CommandStatus.NON_ZERO_EXIT,
        target=SSH_TARGET,
        stderr="remote failure detail",
    )
    assert result.legacy_output == "remote failure detail"


@pytest.mark.parametrize("target", [LOCAL_TARGET, SSH_TARGET])
@pytest.mark.parametrize(
    "status",
    [
        CommandStatus.PERMISSION_DENIED,
        CommandStatus.SSH_AUTH_FAILED,
        CommandStatus.SSH_UNREACHABLE,
        CommandStatus.PARSE_ERROR,
    ],
)
def test_remaining_failure_statuses_fall_back_to_stderr_or_stdout(
    status: CommandStatus, target: str
) -> None:
    """Các status còn lại dùng default: stderr nếu có, fallback stdout."""

    with_stderr = CommandResult(
        status=status, target=target, stdout="out", stderr="err"
    )
    assert with_stderr.legacy_output == "err"

    only_stdout = CommandResult(status=status, target=target, stdout="out")
    assert only_stdout.legacy_output == "out"


@pytest.mark.parametrize("target", [LOCAL_TARGET, SSH_TARGET])
@pytest.mark.parametrize("status", _ALL_STATUSES)
def test_iter_adapter_matches_success_and_legacy_output(
    status: CommandStatus, target: str
) -> None:
    result = CommandResult(status=status, target=target, stdout="x", stderr="y")
    ok, output = result

    assert ok == result.success
    assert output == result.legacy_output


@pytest.mark.parametrize("target", [LOCAL_TARGET, SSH_TARGET])
@pytest.mark.parametrize("status", _ALL_STATUSES)
def test_to_dict_is_json_safe_and_round_trippable(
    status: CommandStatus, target: str
) -> None:
    result = CommandResult(
        status=status,
        exit_code=1,
        stdout="out",
        stderr="err",
        error_type="SomeError",
        command_id="cmd-matrix",
        target=target,
        duration_ms=42,
    )

    payload = result.to_dict()

    assert payload["status"] == status.value
    assert payload["command_id"] == "cmd-matrix"
    assert payload["target"] == target
    assert payload["duration_ms"] == 42
    # Bắt buộc mọi giá trị là kiểu JSON-serializable cơ bản.
    for value in payload.values():
        assert value is None or isinstance(value, (str, int, float, bool))
