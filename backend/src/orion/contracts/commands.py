"""Transport-independent command inputs and observed process outcomes.

These contracts confer no execution permission. Target resolution and scoped
authorization happen before a worker/SSH transport receives the input.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from orion.contracts import CanonicalModel

CommandShell = Literal["powershell", "cmd", "sh", "bash"]
CommandState = Literal[
    "created", "running", "succeeded", "failed", "cancelled", "timed_out", "outcome_unknown"
]


class CommandRunInput(CanonicalModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    target_ref: str = Field(min_length=1, max_length=128)
    shell: CommandShell
    command: str = Field(min_length=1, max_length=65_536, repr=False)
    cwd: str | None = Field(default=None, min_length=1, max_length=4096)
    timeout_seconds: int = Field(default=60, strict=True, ge=1, le=3600)
    max_output_bytes: int = Field(default=262_144, strict=True, ge=1024, le=4_194_304)

    @field_validator("target_ref", "command", "cwd")
    @classmethod
    def valid_text(cls, value: str | None) -> str | None:
        if value is not None and ("\0" in value or not value.strip()):
            raise ValueError("command fields must be nonempty text without NUL")
        return value

    @field_validator("command")
    @classmethod
    def bounded_script(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 65_536:
            raise ValueError("command exceeds UTF-8 byte limit")
        return value

    def payload_hash(self) -> str:
        """Bind approval to every normalized input, without logging script text."""
        payload = json.dumps(
            self.model_dump(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


class CommandObservation(CanonicalModel):
    """An observation, never an instruction to relaunch an existing handle.

    Only a verified process exit supplies exit_code. A timeout/cancel report
    requires observed process-tree termination; otherwise use outcome_unknown.
    Output is transient untrusted evidence; persistence needs a safe projection.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    command_id: str = Field(min_length=1, max_length=128)
    target_ref: str = Field(min_length=1, max_length=128)
    shell: CommandShell
    state: CommandState
    exit_code: int | None = Field(default=None, strict=True)
    stdout: str = Field(default="", max_length=4_194_304, repr=False)
    stderr: str = Field(default="", max_length=4_194_304, repr=False)
    duration_seconds: float = Field(default=0, ge=0, allow_inf_nan=False)
    omitted_output_bytes: int = Field(default=0, strict=True, ge=0)
    process_tree_terminated: bool = False

    @model_validator(mode="after")
    def consistent_outcome(self) -> CommandObservation:
        if self.state == "succeeded" and self.exit_code != 0:
            raise ValueError("succeeded command requires observed exit code zero")
        if self.state == "failed" and (self.exit_code is None or self.exit_code == 0):
            raise ValueError("failed command requires observed nonzero exit code")
        if self.state in {"created", "running", "outcome_unknown"} and self.exit_code is not None:
            raise ValueError("unverified process outcome cannot carry an exit code")
        if self.state in {"cancelled", "timed_out"} and not self.process_tree_terminated:
            raise ValueError("cancel/timeout requires verified process-tree termination")
        if self.state in {"created", "running"} and self.process_tree_terminated:
            raise ValueError("active process cannot have a terminated process tree")
        size = len(self.stdout.encode("utf-8")) + len(self.stderr.encode("utf-8"))
        if size > 4_194_304:
            raise ValueError("combined output exceeds UTF-8 byte limit")
        return self

    @property
    def output_truncated(self) -> bool:
        return self.omitted_output_bytes > 0


class CommandPage(CommandObservation):
    """A bounded byte-cursor observation of transient output, never a replay."""

    stdout_offset: int = Field(default=0, strict=True, ge=0, le=4_194_304)
    stderr_offset: int = Field(default=0, strict=True, ge=0, le=4_194_304)
    next_stdout_offset: int = Field(default=0, strict=True, ge=0, le=4_194_304)
    next_stderr_offset: int = Field(default=0, strict=True, ge=0, le=4_194_304)
    captured_output_bytes: int = Field(default=0, strict=True, ge=0, le=4_194_304)
    output_available: bool = True

    @model_validator(mode="after")
    def valid_cursors(self) -> CommandPage:
        stdout_bytes = self.next_stdout_offset - self.stdout_offset
        stderr_bytes = self.next_stderr_offset - self.stderr_offset
        if (
            not 0 <= stdout_bytes <= 32_768
            or not 0 <= stderr_bytes <= 32_768
            or self.next_stdout_offset + self.next_stderr_offset > self.captured_output_bytes
            or (not self.output_available and (self.stdout or self.stderr))
            or (
                self.output_available
                and (
                    len(self.stdout) > stdout_bytes
                    or len(self.stderr) > stderr_bytes
                    or bool(self.stdout) != bool(stdout_bytes)
                    or bool(self.stderr) != bool(stderr_bytes)
                )
            )
        ):
            raise ValueError("command output cursors are inconsistent")
        return self
