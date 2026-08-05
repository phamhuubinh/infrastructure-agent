from __future__ import annotations

import re
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CommandStatus(str, Enum):
    """Machine-readable outcome of one command execution attempt."""

    SUCCESS = "success"
    EMPTY_SUCCESS = "empty_success"
    COMMAND_NOT_FOUND = "command_not_found"
    PERMISSION_DENIED = "permission_denied"
    TIMEOUT = "timeout"
    SSH_AUTH_FAILED = "ssh_auth_failed"
    SSH_UNREACHABLE = "ssh_unreachable"
    UNSUPPORTED_ENVIRONMENT = "unsupported_environment"
    NON_ZERO_EXIT = "non_zero_exit"
    PARSE_ERROR = "parse_error"


_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(password|passwd|token|api[_-]?key|authorization|private[_-]?key)"
    r"(\s*[:=]\s*)([^\s,;]+)"
)
_BEARER_TOKEN = re.compile(r"(?i)\bBearer\s+[^\s,;]+")
_URL_CREDENTIAL = re.compile(r"(://[^\s:/@]+:)[^\s@]+(@)")


def redact_sensitive(value: str) -> str:
    """Redact common credential forms from serialized diagnostics."""

    value = _BEARER_TOKEN.sub("Bearer <redacted>", value)
    value = _SECRET_ASSIGNMENT.sub(r"\1\2<redacted>", value)
    return _URL_CREDENTIAL.sub(r"\1<redacted>\2", value)


@dataclass(frozen=True, slots=True, repr=False)
class CommandResult:
    """Immutable transport result retaining stdout, stderr and exit metadata.

    ``__iter__`` is a temporary compatibility adapter for legacy callers that
    still unpack ``(ok, output)``. New code should read the named fields.
    """

    status: CommandStatus
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    error_type: str | None = None
    command_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    target: str = "localhost"
    duration_ms: int = 0

    @property
    def success(self) -> bool:
        return self.status in (CommandStatus.SUCCESS, CommandStatus.EMPTY_SUCCESS)

    @property
    def legacy_output(self) -> str:
        """Return the old single-output view during the migration window."""

        if self.success:
            return self.stdout
        if self.status is CommandStatus.COMMAND_NOT_FOUND:
            if self.target == "localhost" or self.error_type == "FileNotFoundError":
                return ""
            return self.stderr or self.stdout
        if self.status in (
            CommandStatus.TIMEOUT,
            CommandStatus.UNSUPPORTED_ENVIRONMENT,
        ):
            return ""
        if self.status is CommandStatus.NON_ZERO_EXIT and self.target == "localhost":
            return ""
        return self.stderr or self.stdout

    def __iter__(self) -> Iterator[bool | str]:
        yield self.success
        yield self.legacy_output

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation with credential redaction."""

        return {
            "status": self.status.value,
            "exit_code": self.exit_code,
            "stdout": redact_sensitive(self.stdout),
            "stderr": redact_sensitive(self.stderr),
            "error_type": self.error_type,
            "command_id": self.command_id,
            "target": redact_sensitive(self.target),
            "duration_ms": self.duration_ms,
        }

    def __repr__(self) -> str:
        return (
            "CommandResult("
            f"status={self.status!r}, exit_code={self.exit_code!r}, "
            f"stdout_len={len(self.stdout)}, stderr_len={len(self.stderr)}, "
            f"error_type={self.error_type!r}, command_id={self.command_id!r}, "
            f"target={redact_sensitive(self.target)!r}, duration_ms={self.duration_ms}"
            ")"
        )
