"""DR1-801 — Unit test matrix cho CapabilityResult.

Bao phủ ma trận local/SSH command_results -> CapabilityStatus
(valid/valid_empty/partial/collection_failed) qua `from_legacy`, cộng với
construction trực tiếp cho các status không sinh từ `from_legacy`
(unsupported/invalid_parameters/parse_failed), theo acceptance criteria
của DR1-801 (coverage branch đủ cho mapping lỗi core).
"""

from __future__ import annotations

import pytest

from src.shared.execution.command_result import CommandResult, CommandStatus
from src.tool.capability_result import CapabilityResult, CapabilityStatus
from src.tool.errors import CapabilityErrorCode

LOCAL_TARGET = "localhost"
SSH_TARGET = "monitor"


def _ok(target: str, stdout: str = "data") -> CommandResult:
    return CommandResult(status=CommandStatus.SUCCESS, target=target, stdout=stdout)


def _empty_ok(target: str) -> CommandResult:
    return CommandResult(status=CommandStatus.EMPTY_SUCCESS, target=target)


def _failed(target: str, status: CommandStatus = CommandStatus.NON_ZERO_EXIT) -> CommandResult:
    return CommandResult(status=status, target=target, stderr="boom")


# ---------------------------------------------------------------------------
# from_legacy: no commands at all -> classified purely by payload emptiness
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"count": 1}, CapabilityStatus.VALID),
        ([{"a": 1}], CapabilityStatus.VALID),
        ("non-empty", CapabilityStatus.VALID),
        (None, CapabilityStatus.VALID_EMPTY),
        ("", CapabilityStatus.VALID_EMPTY),
        ({}, CapabilityStatus.VALID_EMPTY),
        ([], CapabilityStatus.VALID_EMPTY),
        ((), CapabilityStatus.VALID_EMPTY),
    ],
)
def test_from_legacy_without_commands_classifies_by_payload(
    payload: object, expected: CapabilityStatus
) -> None:
    result = CapabilityResult.from_legacy(payload)

    assert result.status is expected
    assert result.success is (expected in (CapabilityStatus.VALID, CapabilityStatus.VALID_EMPTY))
    assert result.capability_error is None


# ---------------------------------------------------------------------------
# from_legacy: single-target (local-only / ssh-only) command matrices
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("target", [LOCAL_TARGET, SSH_TARGET])
def test_all_commands_succeed_with_data_is_valid(target: str) -> None:
    result = CapabilityResult.from_legacy(
        {"value": 1}, command_results=(_ok(target), _ok(target))
    )
    assert result.status is CapabilityStatus.VALID
    assert result.capability_error is None


@pytest.mark.parametrize("target", [LOCAL_TARGET, SSH_TARGET])
def test_all_commands_succeed_empty_payload_is_valid_empty(target: str) -> None:
    result = CapabilityResult.from_legacy(
        [], command_results=(_empty_ok(target),)
    )
    assert result.status is CapabilityStatus.VALID_EMPTY
    assert result.capability_error is None


@pytest.mark.parametrize("target", [LOCAL_TARGET, SSH_TARGET])
@pytest.mark.parametrize(
    "status",
    [
        CommandStatus.COMMAND_NOT_FOUND,
        CommandStatus.PERMISSION_DENIED,
        CommandStatus.TIMEOUT,
        CommandStatus.SSH_AUTH_FAILED,
        CommandStatus.SSH_UNREACHABLE,
        CommandStatus.UNSUPPORTED_ENVIRONMENT,
        CommandStatus.NON_ZERO_EXIT,
        CommandStatus.PARSE_ERROR,
    ],
)
def test_single_failed_command_with_no_data_is_collection_failed(
    status: CommandStatus, target: str
) -> None:
    result = CapabilityResult.from_legacy(
        None, command_results=(_failed(target, status),)
    )

    assert result.status is CapabilityStatus.COLLECTION_FAILED
    assert result.success is False
    assert result.data is None
    assert result.produced_fact_names == ()
    assert result.capability_error is not None


# ---------------------------------------------------------------------------
# from_legacy: mixed local + SSH command matrices (fan-out capabilities)
# ---------------------------------------------------------------------------


def test_local_success_plus_ssh_failure_with_data_is_partial() -> None:
    commands = (_ok(LOCAL_TARGET), _failed(SSH_TARGET, CommandStatus.SSH_UNREACHABLE))

    result = CapabilityResult.from_legacy({"partial": True}, command_results=commands)

    assert result.status is CapabilityStatus.PARTIAL
    assert result.success is False
    assert result.data == {"partial": True}
    assert result.capability_error is not None
    assert result.capability_error.code is CapabilityErrorCode.SSH_UNREACHABLE


def test_ssh_success_plus_local_failure_with_data_is_partial() -> None:
    commands = (_ok(SSH_TARGET), _failed(LOCAL_TARGET, CommandStatus.PERMISSION_DENIED))

    result = CapabilityResult.from_legacy({"partial": True}, command_results=commands)

    assert result.status is CapabilityStatus.PARTIAL
    assert result.capability_error is not None
    assert result.capability_error.code is CapabilityErrorCode.PERMISSION_DENIED


def test_mixed_success_and_failure_but_empty_data_is_collection_failed() -> None:
    """Có succeed command nhưng data rỗng -> vẫn phải collection_failed,
    không được coi là partial (partial yêu cầu data thực sự khác rỗng)."""

    commands = (_ok(LOCAL_TARGET), _failed(SSH_TARGET))

    result = CapabilityResult.from_legacy({}, command_results=commands)

    assert result.status is CapabilityStatus.COLLECTION_FAILED
    assert result.data is None


def test_all_targets_fail_is_collection_failed_regardless_of_target_mix() -> None:
    commands = (
        _failed(LOCAL_TARGET, CommandStatus.TIMEOUT),
        _failed(SSH_TARGET, CommandStatus.SSH_AUTH_FAILED),
    )

    result = CapabilityResult.from_legacy({"ignored": True}, command_results=commands)

    # First failed command drives the mapped error (order-preserving).
    assert result.status is CapabilityStatus.COLLECTION_FAILED
    assert result.capability_error is not None
    assert result.capability_error.code is CapabilityErrorCode.TIMEOUT


# ---------------------------------------------------------------------------
# Direct construction: statuses not reachable via from_legacy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "expected_code"),
    [
        (CapabilityStatus.UNSUPPORTED, CapabilityErrorCode.UNSUPPORTED_ENVIRONMENT),
        (CapabilityStatus.INVALID_PARAMETERS, CapabilityErrorCode.INVALID_PARAMETERS),
        (CapabilityStatus.PARSE_FAILED, CapabilityErrorCode.PARSE_ERROR),
    ],
)
def test_directly_constructed_failure_statuses_populate_capability_error(
    status: CapabilityStatus, expected_code: CapabilityErrorCode
) -> None:
    result = CapabilityResult(status=status)

    assert result.success is False
    assert result.is_valid is False
    assert result.capability_error is not None
    assert result.capability_error.code is expected_code


@pytest.mark.parametrize("target", [LOCAL_TARGET, SSH_TARGET])
def test_directly_constructed_failure_prefers_command_error_over_status(
    target: str,
) -> None:
    """Nếu có command_results kèm status generic, lỗi command cụ thể (vd
    SSH_UNREACHABLE) phải thắng lỗi status chung (collection_failed)."""

    command = _failed(target, CommandStatus.SSH_UNREACHABLE)
    result = CapabilityResult(
        status=CapabilityStatus.COLLECTION_FAILED,
        command_results=(command,),
        error="collection failed",
    )

    assert result.capability_error is not None
    assert result.capability_error.code is CapabilityErrorCode.SSH_UNREACHABLE


def test_valid_statuses_never_get_capability_error_even_if_explicit() -> None:
    for status in (CapabilityStatus.VALID, CapabilityStatus.VALID_EMPTY):
        result = CapabilityResult(status=status)
        assert result.capability_error is None
