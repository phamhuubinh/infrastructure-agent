from __future__ import annotations

import os
import shlex
import subprocess
import time as _time
from abc import ABC, abstractmethod

from src.shared.execution.command_result import CommandResult, CommandStatus
from src.shared.logger import error, info, warning


def _stream_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace").strip()
    return value.strip()


_SSH_AUTH_MARKERS = (
    "permission denied (publickey",
    "permission denied, please try again",
    "authentication failed",
    "too many authentication failures",
    "password:",
)
_SSH_UNREACHABLE_MARKERS = (
    "connection refused",
    "connection closed",
    "connection reset",
    "could not resolve hostname",
    "name or service not known",
    "no route to host",
    "network is unreachable",
    "host is down",
)
_SSH_TIMEOUT_MARKERS = (
    "connection timed out",
    "operation timed out",
    "connect to host",
)
_REMOTE_COMMAND_NOT_FOUND_MARKERS = (
    "command not found",
    "not found",
)


def _classify_ssh_failure(exit_code: int, stderr: str) -> CommandStatus:
    """Classify an ssh CLI/remote failure at the transport adapter boundary."""

    lowered = stderr.lower()
    if any(marker in lowered for marker in _SSH_AUTH_MARKERS):
        return CommandStatus.SSH_AUTH_FAILED
    if any(marker in lowered for marker in _SSH_UNREACHABLE_MARKERS):
        return CommandStatus.SSH_UNREACHABLE
    if "timed out" in lowered or (
        exit_code == 255 and any(marker in lowered for marker in _SSH_TIMEOUT_MARKERS)
    ):
        return CommandStatus.TIMEOUT
    if exit_code == 127 or any(
        marker in lowered for marker in _REMOTE_COMMAND_NOT_FOUND_MARKERS
    ):
        return CommandStatus.COMMAND_NOT_FOUND
    if exit_code == 126 or "permission denied" in lowered:
        return CommandStatus.PERMISSION_DENIED
    return CommandStatus.NON_ZERO_EXIT


class ExecutionBackend(ABC):
    """Interface for command execution transport."""

    @abstractmethod
    def run(
        self,
        command: list[str],
        timeout: int = 5,
    ) -> CommandResult: ...


class LocalExecutionBackend(ExecutionBackend):
    """Run commands on the local machine via subprocess."""

    def run(
        self,
        command: list[str],
        timeout: int = 5,
    ) -> CommandResult:
        _t0 = _time.monotonic()
        cmd_str = " ".join(command) if command else ""
        if not command:
            return CommandResult(
                status=CommandStatus.COMMAND_NOT_FOUND,
                stderr="No command specified.",
                error_type="EmptyCommand",
                target="localhost",
            )
        stable_env = dict(os.environ)
        stable_env.update({"LANG": "C", "LC_ALL": "C"})
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                env=stable_env,
            )
        except subprocess.TimeoutExpired as exc:
            _dur = int((_time.monotonic() - _t0) * 1000)
            error(
                "exec",
                command=cmd_str,
                status="failed",
                error=str(exc),
                host="localhost",
                message="Failed",
            )
            return CommandResult(
                status=CommandStatus.TIMEOUT,
                stdout=_stream_text(exc.stdout),
                stderr=_stream_text(exc.stderr) or str(exc),
                error_type=type(exc).__name__,
                target="localhost",
                duration_ms=_dur,
            )
        except PermissionError as exc:
            _dur = int((_time.monotonic() - _t0) * 1000)
            error(
                "exec",
                command=cmd_str,
                status=CommandStatus.PERMISSION_DENIED.value,
                error=str(exc),
                host="localhost",
                message="Failed",
            )
            return CommandResult(
                status=CommandStatus.PERMISSION_DENIED,
                stderr=str(exc),
                error_type=type(exc).__name__,
                target="localhost",
                duration_ms=_dur,
            )
        except OSError as exc:
            _dur = int((_time.monotonic() - _t0) * 1000)
            status = CommandStatus.COMMAND_NOT_FOUND
            error(
                "exec",
                command=cmd_str,
                status=status.value,
                error=str(exc),
                host="localhost",
                message="Failed",
            )
            return CommandResult(
                status=status,
                stderr=str(exc),
                error_type=type(exc).__name__,
                target="localhost",
                duration_ms=_dur,
            )

        if completed.returncode != 0:
            _dur = int((_time.monotonic() - _t0) * 1000)
            # Non-zero exit is not necessarily an error
            # (e.g. service not running, command not found on target).
            # Use WARNING — only truly fatal failures (OSError, TimeoutExpired)
            # should be ERROR.
            warning(
                "exec",
                command=cmd_str,
                status="non-zero",
                returncode=completed.returncode,
                host="localhost",
                message="Non-zero exit",
            )
            status = (
                CommandStatus.PERMISSION_DENIED
                if completed.returncode == 126
                or "permission denied" in completed.stderr.lower()
                else CommandStatus.NON_ZERO_EXIT
            )
            return CommandResult(
                status=status,
                exit_code=completed.returncode,
                stdout=completed.stdout.strip(),
                stderr=getattr(completed, "stderr", "").strip(),
                error_type="NonZeroExit",
                target="localhost",
                duration_ms=_dur,
            )

        _dur = int((_time.monotonic() - _t0) * 1000)
        info(
            "exec",
            command=cmd_str,
            status="success",
            duration_ms=_dur,
            host="localhost",
            message="Completed",
        )
        stdout = completed.stdout.strip()
        return CommandResult(
            status=(CommandStatus.SUCCESS if stdout else CommandStatus.EMPTY_SUCCESS),
            exit_code=completed.returncode,
            stdout=stdout,
            stderr=getattr(completed, "stderr", "").strip(),
            target="localhost",
            duration_ms=_dur,
        )


class SSHExecutionBackend(ExecutionBackend):
    """Run commands on a remote machine via SSH CLI."""

    def __init__(
        self,
        host: str,
        user: str = "root",
        port: int = 22,
        identity_file: str | None = None,
        strict_host_key_checking: bool = False,
    ) -> None:
        self._host = host
        self._user = user
        self._port = port
        self._identity_file = identity_file
        self._strict_host_key_checking = strict_host_key_checking

    def _build_ssh_command(
        self,
        remote_command: list[str],
    ) -> list[str]:
        strict = "yes" if self._strict_host_key_checking else "no"
        known_hosts_file = (
            "~/.ssh/known_hosts" if self._strict_host_key_checking else "/dev/null"
        )
        parts: list[str] = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            "-o",
            f"StrictHostKeyChecking={strict}",
            "-o",
            f"UserKnownHostsFile={known_hosts_file}",
            "-p",
            str(self._port),
        ]
        if self._identity_file is not None:
            parts.extend(["-i", self._identity_file])
        parts.append(f"{self._user}@{self._host}")
        parts.append(shlex.join(remote_command))
        return parts

    def run(
        self,
        command: list[str],
        timeout: int = 5,
    ) -> CommandResult:
        _t0 = _time.monotonic()
        ssh_cmd = self._build_ssh_command(command)
        cmd_str = " ".join(command) if command else ""
        host = self._host
        try:
            completed = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            _dur = int((_time.monotonic() - _t0) * 1000)
            error(
                "exec",
                command=cmd_str,
                status="failed",
                error=str(exc),
                host=host,
                message="Failed",
            )
            return CommandResult(
                status=CommandStatus.TIMEOUT,
                stderr=str(exc),
                error_type=type(exc).__name__,
                target=host,
                duration_ms=_dur,
            )
        except OSError as exc:
            _dur = int((_time.monotonic() - _t0) * 1000)
            error(
                "exec",
                command=cmd_str,
                status="failed",
                error=str(exc),
                host=host,
                message="Failed",
            )
            return CommandResult(
                status=(
                    CommandStatus.COMMAND_NOT_FOUND
                    if isinstance(exc, FileNotFoundError)
                    else CommandStatus.UNSUPPORTED_ENVIRONMENT
                ),
                stderr=str(exc),
                error_type=type(exc).__name__,
                target=host,
                duration_ms=_dur,
            )

        if completed.returncode != 0:
            _dur = int((_time.monotonic() - _t0) * 1000)
            completed_stderr = getattr(completed, "stderr", "")
            err_msg = completed_stderr.strip() or completed.stdout.strip()
            status = _classify_ssh_failure(completed.returncode, err_msg)
            if status is CommandStatus.SSH_AUTH_FAILED:
                error(
                    "exec",
                    command=cmd_str,
                    status="failed",
                    error="SSH authentication failed",
                    host=host,
                    message="Failed",
                )
                return CommandResult(
                    status=status,
                    exit_code=completed.returncode,
                    stdout=completed.stdout.strip(),
                    stderr=(
                        "SSH authentication failed (password/public-key rejected). "
                        "Use valid SSH key authentication."
                    ),
                    error_type="SSHAuthenticationError",
                    target=host,
                    duration_ms=_dur,
                )
            # Non-zero exit is not necessarily an error
            # (e.g. service not running, command not found on target).
            # Use WARNING — only truly fatal failures (OSError, TimeoutExpired)
            # should be ERROR.
            warning(
                "exec",
                command=cmd_str,
                status="non-zero",
                returncode=completed.returncode,
                error=err_msg,
                host=host,
                message="Non-zero exit",
            )
            return CommandResult(
                status=status,
                exit_code=completed.returncode,
                stdout=completed.stdout.strip(),
                stderr=err_msg,
                error_type=(
                    "RemoteNonZeroExit"
                    if status is CommandStatus.NON_ZERO_EXIT
                    else status.name
                ),
                target=host,
                duration_ms=_dur,
            )

        _dur = int((_time.monotonic() - _t0) * 1000)
        info(
            "exec",
            command=cmd_str,
            status="success",
            duration_ms=_dur,
            host=host,
            message="Completed",
        )
        stdout = completed.stdout.strip()
        return CommandResult(
            status=(CommandStatus.SUCCESS if stdout else CommandStatus.EMPTY_SUCCESS),
            exit_code=completed.returncode,
            stdout=stdout,
            stderr=getattr(completed, "stderr", "").strip(),
            target=host,
            duration_ms=_dur,
        )
