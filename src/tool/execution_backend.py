from __future__ import annotations

import shlex
import subprocess
import time as _time
from abc import ABC, abstractmethod

from src.shared.logger import error, info


class ExecutionBackend(ABC):
    """Interface for command execution transport."""

    @abstractmethod
    def run(
        self,
        command: list[str],
        timeout: int = 5,
    ) -> tuple[bool, str]: ...


class LocalExecutionBackend(ExecutionBackend):
    """Run commands on the local machine via subprocess."""

    def run(
        self,
        command: list[str],
        timeout: int = 5,
    ) -> tuple[bool, str]:
        _t0 = _time.monotonic()
        cmd_str = " ".join(command) if command else ""
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            _dur = int((_time.monotonic() - _t0) * 1000)
            error(
                "exec",
                command=cmd_str,
                status="failed",
                error=str(exc),
                host="localhost",
                message="Failed",
            )
            return False, ""

        if completed.returncode != 0:
            _dur = int((_time.monotonic() - _t0) * 1000)
            error(
                "exec",
                command=cmd_str,
                status="failed",
                returncode=completed.returncode,
                host="localhost",
                message="Failed",
            )
            return False, ""

        _dur = int((_time.monotonic() - _t0) * 1000)
        info(
            "exec",
            command=cmd_str,
            status="success",
            duration_ms=_dur,
            host="localhost",
            message="Completed",
        )
        return True, completed.stdout.strip()


class SSHExecutionBackend(ExecutionBackend):
    """Run commands on a remote machine via SSH CLI."""

    def __init__(
        self,
        host: str,
        user: str = "root",
        port: int = 22,
        identity_file: str | None = None,
    ) -> None:
        self._host = host
        self._user = user
        self._port = port
        self._identity_file = identity_file

    def _build_ssh_command(
        self,
        remote_command: list[str],
    ) -> list[str]:
        parts: list[str] = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            # Intentional: trusted local network only.
            # StrictHostKeyChecking=no + UserKnownHostsFile=/dev/null
            # avoids interactive prompts on first connection and host key
            # rotation without manual cleanup. Not suitable for internet-facing
            # deployments — see ADR in docs/ai/09_ARCHITECTURE_DECISIONS.md.
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
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
    ) -> tuple[bool, str]:
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
        except (OSError, subprocess.TimeoutExpired) as exc:
            _dur = int((_time.monotonic() - _t0) * 1000)
            error(
                "exec",
                command=cmd_str,
                status="failed",
                error=str(exc),
                host=host,
                message="Failed",
            )
            return False, ""

        if completed.returncode != 0:
            _dur = int((_time.monotonic() - _t0) * 1000)
            err_msg = completed.stderr.strip() or completed.stdout.strip()
            if "password" in completed.stderr.lower():
                error(
                    "exec",
                    command=cmd_str,
                    status="failed",
                    error="SSH authentication failed (password prompted)",
                    host=host,
                    message="Failed",
                )
                return (
                    False,
                    "SSH authentication failed (password prompted). Use SSH key authentication.",
                )
            error(
                "exec",
                command=cmd_str,
                status="failed",
                error=err_msg,
                host=host,
                message="Failed",
            )
            return False, err_msg

        _dur = int((_time.monotonic() - _t0) * 1000)
        info(
            "exec",
            command=cmd_str,
            status="success",
            duration_ms=_dur,
            host=host,
            message="Completed",
        )
        return True, completed.stdout.strip()
