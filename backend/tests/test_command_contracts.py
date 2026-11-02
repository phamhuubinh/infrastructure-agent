from __future__ import annotations

import pytest
from pydantic import ValidationError

from orion.contracts.commands import CommandObservation, CommandRunInput


def test_approval_fingerprint_binds_all_inputs_without_classifying_shell_text():
    original = CommandRunInput(target_ref="worker-a", shell="powershell", command="Get-Date")
    assert original.payload_hash() == CommandRunInput(**original.model_dump()).payload_hash()
    changes = {
        "target_ref": "worker-b",
        "shell": "cmd",
        "command": "Get-Date; Remove-Item example",
        "cwd": "C:/a folder",
        "timeout_seconds": 61,
        "max_output_bytes": 1024,
    }
    for field, value in changes.items():
        changed = CommandRunInput(**{**original.model_dump(), field: value})
        assert changed.payload_hash() != original.payload_hash()
    assert "Get-Date" not in repr(original)


@pytest.mark.parametrize(
    "change",
    [
        {"command": " "},
        {"command": "a\0b"},
        {"command": "秘" * 30_000},
        {"shell": "python"},
        {"target_ref": ""},
        {"cwd": "\0"},
        {"timeout_seconds": True},
        {"timeout_seconds": 3601},
        {"max_output_bytes": 0},
        {"max_output_bytes": 4_194_305},
        {"elevate": True},
        {"read_only": True},
    ],
)
def test_command_rejects_invalid_bounds_and_model_authority_fields(change):
    with pytest.raises(ValidationError):
        CommandRunInput(**{"target_ref": "worker-a", "shell": "sh", "command": "pwd", **change})


@pytest.mark.parametrize(
    "change",
    [
        {"state": "succeeded"},
        {"state": "succeeded", "exit_code": 1},
        {"state": "failed"},
        {"state": "failed", "exit_code": 0},
        {"state": "running", "exit_code": 0},
        {"state": "outcome_unknown", "exit_code": 0},
        {"state": "cancelled"},
        {"state": "timed_out"},
        {"state": "running", "process_tree_terminated": True},
        {"duration_seconds": float("nan")},
        {"duration_seconds": float("inf")},
        {"stdout": "秘" * 1_000_000, "stderr": "秘" * 1_000_000},
    ],
)
def test_observations_cannot_claim_unverified_success_or_termination(change):
    with pytest.raises(ValidationError):
        CommandObservation(
            **{
                "command_id": "cmd-a",
                "target_ref": "worker-a",
                "shell": "sh",
                "state": "outcome_unknown",
                **change,
            }
        )


def test_partial_output_and_unknown_outcome_are_explicit():
    result = CommandObservation(
        command_id="cmd-a",
        target_ref="worker-a",
        shell="bash",
        state="outcome_unknown",
        stdout="partial 秘",
        omitted_output_bytes=200,
    )
    assert result.output_truncated
    assert result.exit_code is None
    assert result.model_dump()["stdout"] == "partial 秘"
    assert "partial" not in repr(result)
    cancelled = CommandObservation(
        command_id="cmd-b",
        target_ref="worker-a",
        shell="cmd",
        state="cancelled",
        process_tree_terminated=True,
    )
    assert cancelled.exit_code is None
