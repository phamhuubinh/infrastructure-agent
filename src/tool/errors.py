from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.shared.execution.command_result import (
    CommandResult,
    CommandStatus,
    redact_sensitive,
)


class CapabilityErrorCategory(str, Enum):
    """Stable error families used by fallback and retry policy."""

    TRANSPORT = "transport"
    ENVIRONMENT = "environment"
    COMMAND = "command"
    PARAMETER = "parameter"
    PARSER = "parser"
    SOURCE_API = "source_api"
    INTERNAL = "internal"


class CapabilityErrorCode(str, Enum):
    """Machine-readable capability errors; messages are never policy inputs."""

    COMMAND_NOT_FOUND = "command_not_found"
    PERMISSION_DENIED = "permission_denied"
    TIMEOUT = "timeout"
    SSH_AUTH_FAILED = "ssh_auth_failed"
    SSH_UNREACHABLE = "ssh_unreachable"
    UNSUPPORTED_ENVIRONMENT = "unsupported_environment"
    NON_ZERO_EXIT = "non_zero_exit"
    PARSE_ERROR = "parse_error"
    INVALID_PARAMETERS = "invalid_parameters"
    SOURCE_API_ERROR = "source_api_error"
    COLLECTION_FAILED = "collection_failed"
    INTERNAL_ERROR = "internal_error"


@dataclass(frozen=True, slots=True, repr=False)
class CapabilityError:
    """Safe structured failure attached to capability and tool results."""

    code: CapabilityErrorCode
    category: CapabilityErrorCategory
    message: str
    recoverable: bool
    command_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "category": self.category.value,
            "message": redact_sensitive(self.message),
            "recoverable": self.recoverable,
            "command_id": self.command_id,
        }

    def __repr__(self) -> str:
        return (
            "CapabilityError("
            f"code={self.code!r}, category={self.category!r}, "
            f"recoverable={self.recoverable!r}, command_id={self.command_id!r}"
            ")"
        )


_COMMAND_ERROR_POLICY: dict[
    CommandStatus,
    tuple[CapabilityErrorCode, CapabilityErrorCategory, bool],
] = {
    CommandStatus.COMMAND_NOT_FOUND: (
        CapabilityErrorCode.COMMAND_NOT_FOUND,
        CapabilityErrorCategory.ENVIRONMENT,
        False,
    ),
    CommandStatus.PERMISSION_DENIED: (
        CapabilityErrorCode.PERMISSION_DENIED,
        CapabilityErrorCategory.ENVIRONMENT,
        False,
    ),
    CommandStatus.TIMEOUT: (
        CapabilityErrorCode.TIMEOUT,
        CapabilityErrorCategory.TRANSPORT,
        True,
    ),
    CommandStatus.SSH_AUTH_FAILED: (
        CapabilityErrorCode.SSH_AUTH_FAILED,
        CapabilityErrorCategory.TRANSPORT,
        False,
    ),
    CommandStatus.SSH_UNREACHABLE: (
        CapabilityErrorCode.SSH_UNREACHABLE,
        CapabilityErrorCategory.TRANSPORT,
        True,
    ),
    CommandStatus.UNSUPPORTED_ENVIRONMENT: (
        CapabilityErrorCode.UNSUPPORTED_ENVIRONMENT,
        CapabilityErrorCategory.ENVIRONMENT,
        False,
    ),
    CommandStatus.NON_ZERO_EXIT: (
        CapabilityErrorCode.NON_ZERO_EXIT,
        CapabilityErrorCategory.COMMAND,
        False,
    ),
    CommandStatus.PARSE_ERROR: (
        CapabilityErrorCode.PARSE_ERROR,
        CapabilityErrorCategory.PARSER,
        False,
    ),
}


def command_error_from_result(result: CommandResult) -> CapabilityError | None:
    """Map a backend outcome to capability policy without parsing text."""

    policy = _COMMAND_ERROR_POLICY.get(result.status)
    if policy is None:
        return None
    code, category, recoverable = policy
    return CapabilityError(
        code=code,
        category=category,
        message=f"Command collection failed: {result.status.value}",
        recoverable=recoverable,
        command_id=result.command_id,
    )


def capability_error_from_status(
    status: str,
    *,
    command_results: tuple[CommandResult, ...] = (),
    message: str | None = None,
) -> CapabilityError | None:
    """Derive a capability error from status and exact command outcomes."""

    for result in command_results:
        error = command_error_from_result(result)
        if error is not None:
            return error

    if status in ("valid", "valid_empty"):
        return None

    mappings: dict[
        str,
        tuple[CapabilityErrorCode, CapabilityErrorCategory, bool, str],
    ] = {
        "unsupported": (
            CapabilityErrorCode.UNSUPPORTED_ENVIRONMENT,
            CapabilityErrorCategory.ENVIRONMENT,
            False,
            "Capability is unsupported in this environment",
        ),
        "invalid_parameters": (
            CapabilityErrorCode.INVALID_PARAMETERS,
            CapabilityErrorCategory.PARAMETER,
            False,
            "Capability parameters are invalid",
        ),
        "parse_failed": (
            CapabilityErrorCode.PARSE_ERROR,
            CapabilityErrorCategory.PARSER,
            False,
            "Capability output could not be parsed",
        ),
        "partial": (
            CapabilityErrorCode.COLLECTION_FAILED,
            CapabilityErrorCategory.COMMAND,
            False,
            "Capability collection is partial",
        ),
        "collection_failed": (
            CapabilityErrorCode.COLLECTION_FAILED,
            CapabilityErrorCategory.COMMAND,
            False,
            "Capability collection failed",
        ),
    }
    mapped = mappings.get(status)
    if mapped is None:
        return CapabilityError(
            code=CapabilityErrorCode.INTERNAL_ERROR,
            category=CapabilityErrorCategory.INTERNAL,
            message=message or "Internal capability error",
            recoverable=False,
        )
    code, category, recoverable, default_message = mapped
    return CapabilityError(
        code=code,
        category=category,
        message=message or default_message,
        recoverable=recoverable,
    )


def source_api_error(message: str, *, recoverable: bool = True) -> CapabilityError:
    """Create an explicit source-API failure without message classification."""

    return CapabilityError(
        code=CapabilityErrorCode.SOURCE_API_ERROR,
        category=CapabilityErrorCategory.SOURCE_API,
        message=message,
        recoverable=recoverable,
    )


def internal_error(message: str) -> CapabilityError:
    return CapabilityError(
        code=CapabilityErrorCode.INTERNAL_ERROR,
        category=CapabilityErrorCategory.INTERNAL,
        message=message,
        recoverable=False,
    )
