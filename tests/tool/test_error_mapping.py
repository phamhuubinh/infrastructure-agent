from __future__ import annotations

import pytest

from src.shared.execution.command_result import CommandResult, CommandStatus
from src.tool.capability_result import CapabilityResult, CapabilityStatus
from src.tool.errors import (
    CapabilityErrorCategory,
    CapabilityErrorCode,
    capability_error_from_status,
    command_error_from_result,
    internal_error,
    source_api_error,
)


@pytest.mark.parametrize(
    ("status", "code", "category", "recoverable"),
    [
        (
            CommandStatus.COMMAND_NOT_FOUND,
            CapabilityErrorCode.COMMAND_NOT_FOUND,
            CapabilityErrorCategory.ENVIRONMENT,
            False,
        ),
        (
            CommandStatus.PERMISSION_DENIED,
            CapabilityErrorCode.PERMISSION_DENIED,
            CapabilityErrorCategory.ENVIRONMENT,
            False,
        ),
        (
            CommandStatus.TIMEOUT,
            CapabilityErrorCode.TIMEOUT,
            CapabilityErrorCategory.TRANSPORT,
            True,
        ),
        (
            CommandStatus.SSH_AUTH_FAILED,
            CapabilityErrorCode.SSH_AUTH_FAILED,
            CapabilityErrorCategory.TRANSPORT,
            False,
        ),
        (
            CommandStatus.SSH_UNREACHABLE,
            CapabilityErrorCode.SSH_UNREACHABLE,
            CapabilityErrorCategory.TRANSPORT,
            True,
        ),
        (
            CommandStatus.UNSUPPORTED_ENVIRONMENT,
            CapabilityErrorCode.UNSUPPORTED_ENVIRONMENT,
            CapabilityErrorCategory.ENVIRONMENT,
            False,
        ),
        (
            CommandStatus.NON_ZERO_EXIT,
            CapabilityErrorCode.NON_ZERO_EXIT,
            CapabilityErrorCategory.COMMAND,
            False,
        ),
        (
            CommandStatus.PARSE_ERROR,
            CapabilityErrorCode.PARSE_ERROR,
            CapabilityErrorCategory.PARSER,
            False,
        ),
    ],
)
def test_command_status_has_exact_machine_mapping(
    status: CommandStatus,
    code: CapabilityErrorCode,
    category: CapabilityErrorCategory,
    recoverable: bool,
) -> None:
    result = CommandResult(status=status, command_id="cmd-7")

    error = command_error_from_result(result)

    assert error is not None
    assert error.code is code
    assert error.category is category
    assert error.recoverable is recoverable
    assert error.command_id == "cmd-7"


@pytest.mark.parametrize(
    "status", [CommandStatus.SUCCESS, CommandStatus.EMPTY_SUCCESS]
)
def test_successful_command_has_no_error(status: CommandStatus) -> None:
    assert command_error_from_result(CommandResult(status=status)) is None


@pytest.mark.parametrize(
    ("status", "code", "category"),
    [
        (
            CapabilityStatus.INVALID_PARAMETERS,
            CapabilityErrorCode.INVALID_PARAMETERS,
            CapabilityErrorCategory.PARAMETER,
        ),
        (
            CapabilityStatus.UNSUPPORTED,
            CapabilityErrorCode.UNSUPPORTED_ENVIRONMENT,
            CapabilityErrorCategory.ENVIRONMENT,
        ),
        (
            CapabilityStatus.PARSE_FAILED,
            CapabilityErrorCode.PARSE_ERROR,
            CapabilityErrorCategory.PARSER,
        ),
        (
            CapabilityStatus.COLLECTION_FAILED,
            CapabilityErrorCode.COLLECTION_FAILED,
            CapabilityErrorCategory.COMMAND,
        ),
    ],
)
def test_capability_status_has_exact_machine_mapping(
    status: CapabilityStatus,
    code: CapabilityErrorCode,
    category: CapabilityErrorCategory,
) -> None:
    error = capability_error_from_status(status.value)

    assert error is not None
    assert error.code is code
    assert error.category is category
    assert error.recoverable is False


def test_source_api_error_is_explicit_and_recoverable() -> None:
    error = source_api_error("provider unavailable")

    assert error.code is CapabilityErrorCode.SOURCE_API_ERROR
    assert error.category is CapabilityErrorCategory.SOURCE_API
    assert error.recoverable is True


def test_internal_error_is_explicit_and_not_recoverable() -> None:
    error = internal_error("unexpected adapter state")

    assert error.code is CapabilityErrorCode.INTERNAL_ERROR
    assert error.category is CapabilityErrorCategory.INTERNAL
    assert error.recoverable is False


def test_command_mapping_takes_precedence_over_generic_capability_status() -> None:
    command = CommandResult(status=CommandStatus.TIMEOUT, command_id="cmd-timeout")
    result = CapabilityResult(
        status=CapabilityStatus.COLLECTION_FAILED,
        command_results=(command,),
        error="collection failed",
    )

    assert result.capability_error is not None
    assert result.capability_error.code is CapabilityErrorCode.TIMEOUT
    assert result.capability_error.recoverable is True


def test_error_serialization_redacts_credentials_and_repr_omits_message() -> None:
    error = source_api_error("token=secret-value provider unavailable")

    serialized = error.to_dict()

    assert "secret-value" not in str(serialized)
    assert "secret-value" not in repr(error)
    assert "provider unavailable" not in repr(error)
