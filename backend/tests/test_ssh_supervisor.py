"""Supervisor validation/platform gate; real Linux death/cleanup remains external."""

from __future__ import annotations

import json
import sys

import pytest

from orion.integrations.ssh.supervisor import _arguments, supervise


def values(**changes):
    return {
        "shell": "/bin/sh",
        "script": "/private/command.sh",
        "cwd": None,
        "timeout_seconds": 60,
        "parent_pid": 123,
        "metadata_fd": 3,
        **changes,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"shell": "sh; touch /tmp/marker"},
        {"shell": "/private/model-interpreter"},
        {"script": "relative/command.sh"},
        {"script": "/private/../unknown"},
        {"script": "\0/private/script"},
        {"cwd": {"model": "object"}},
        {"timeout_seconds": True},
        {"timeout_seconds": 3601},
        {"metadata_fd": 1},
        {"parent_pid": -1},
        {"arbitrary_pid": 123},
    ],
)
def test_supervisor_rejects_unowned_interpreter_fd_pid_and_ambiguous_input(changes):
    with pytest.raises(ValueError):
        _arguments(json.dumps(values(**changes)))


def test_supervisor_accepts_only_closed_bounded_administrative_parameters():
    original = values(cwd="/folder with spaces", shell="/bin/bash")
    assert _arguments(json.dumps(original)) == original


def test_non_linux_gate_precedes_input_or_process_side_effects(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    with pytest.raises(OSError, match="Linux supervisor is unavailable"):
        supervise("not even JSON")
