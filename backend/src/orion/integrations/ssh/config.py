"""Closed administrative SSH targets; no implicit workstation credential discovery."""

from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from orion.persistence.private_files import checked_path

TargetRef = Annotated[str, Field(pattern=r"^ssh:[a-z][a-z0-9._-]{0,63}$")]
Alias = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")]
MAX_CONFIG_BYTES = 65_536
REMOTE_BOOTSTRAP = "python3 -u -c " + shlex.quote(
    "import sys; n=int(sys.stdin.buffer.readline(16)); "
    "assert 0<n<=131072; source=sys.stdin.buffer.read(n); "
    "assert len(source)==n; exec(compile(source,'<orion-ssh-helper>','exec'))"
)


class SSHConfigurationError(ValueError):
    def __init__(self) -> None:
        super().__init__("SSH command configuration is unavailable.")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)


class SSHTarget(_Strict):
    target_ref: TargetRef
    ssh_alias: Alias = Field(repr=False)
    config_file: str = Field(min_length=1, max_length=4096, repr=False)
    known_hosts_file: str = Field(min_length=1, max_length=4096, repr=False)
    commands: bool = False

    @field_validator("config_file", "known_hosts_file")
    @classmethod
    def absolute_path(cls, value: str) -> str:
        if not Path(value).is_absolute() or any(char in value for char in "\0\r\n"):
            raise ValueError("SSH paths must be absolute server paths")
        return value

    @field_validator("known_hosts_file")
    @classmethod
    def exact_known_hosts(cls, value: str) -> str:
        if any(char in value for char in '%$"'):
            raise ValueError("SSH known-hosts expansion is unavailable")
        return value


class SSHConfiguration(_Strict):
    format_version: Literal[1]
    targets: tuple[SSHTarget, ...] = Field(default=(), max_length=16)

    @field_validator("format_version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("SSH format version must be an integer")
        return value

    @model_validator(mode="after")
    def unique_targets(self) -> SSHConfiguration:
        if len({target.target_ref for target in self.targets}) != len(self.targets):
            raise ValueError("duplicate SSH target")
        return self

    def enabled_target(self, target_ref: str) -> SSHTarget | None:
        return next((t for t in self.targets if t.target_ref == target_ref and t.commands), None)


def load_configuration(path: Path | None = None) -> SSHConfiguration:
    """Unset means disabled; invalid explicit files give a category-only error."""
    if path is None:
        configured = os.getenv("ORION_SSH_COMMAND_CONFIG")
        if not configured:
            return SSHConfiguration(format_version=1)
        path = Path(configured)
    try:
        info = checked_path(path)
        if info.st_size > MAX_CONFIG_BYTES:
            raise ValueError("oversized")
        # JSON validation accepts a JSON array for the immutable tuple, whereas
        # Python strict validation deliberately rejects list coercion.
        return SSHConfiguration.model_validate_json(path.read_bytes())
    except (OSError, ValueError):
        raise SSHConfigurationError() from None


def ssh_argv(target: SSHTarget, executable: str) -> list[str]:
    """Only fixed helper commands belong here; script text travels over stdin."""
    if not target.commands:
        raise PermissionError("SSH commands are disabled")
    if not Path(executable).is_absolute() or any(char in executable for char in "\0\r\n"):
        raise ValueError("SSH transport invocation is unavailable")
    options = {
        "BatchMode": "yes",
        "StrictHostKeyChecking": "yes",
        "UserKnownHostsFile": target.known_hosts_file,
        "GlobalKnownHostsFile": "none",
        "UpdateHostKeys": "no",
        "ConnectTimeout": "10",
        "ConnectionAttempts": "1",
        "ServerAliveInterval": "10",
        "ServerAliveCountMax": "2",
        "ClearAllForwardings": "yes",
        "ForwardAgent": "no",
        "ForwardX11": "no",
        "PermitLocalCommand": "no",
        "RemoteCommand": "none",
        "RequestTTY": "no",
        "StdinNull": "no",
        "SessionType": "default",
        "ControlMaster": "no",
        "ControlPath": "none",
        "EscapeChar": "none",
        "LogLevel": "ERROR",
    }
    # ssh_config-style option values need quotes for paths containing spaces;
    # this is an argv item, never local shell syntax. Reject quote/backslash
    # ambiguity in this one option by using forward-slash paths.
    hosts = target.known_hosts_file.replace("\\", "/")
    if '"' in hosts:
        raise ValueError("SSH known-hosts path is unavailable")
    options["UserKnownHostsFile"] = f'"{hosts}"'
    argv = [executable, "-T", "-F", target.config_file]
    for name, value in options.items():
        argv.extend(("-o", f"{name}={value}"))
    return [*argv, "--", target.ssh_alias, REMOTE_BOOTSTRAP]
