"""Provenance parser/platform gates; filesystem pruning needs native Linux."""

import sys

import pytest

from orion.integrations.ssh.remote_files import PrivateScripts, process_fields, validate_record

IDENTITY = "a" * 32


def record(**changes):
    return {
        "format": "orion-ssh-script",
        "version": 1,
        "uid": 1000,
        "command_id": IDENTITY,
        "helper_pid": 1,
        "start_ticks": 123,
        "boot_id": "12345678-1234-1234-1234-123456789abc",
        "script": "command.sh",
        **changes,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"uid": True},
        {"uid": 999},
        {"version": True},
        {"script": "../../outside"},
        {"script": ["command.sh"]},
        {"helper_pid": False},
        {"helper_pid": -1},
        {"start_ticks": 0},
        {"boot_id": "other boot"},
        {"command_id": "b" * 32},
        {"extra": "not cleanup authority"},
    ],
)
def test_untrusted_marker_grants_no_cleanup_authority(changes):
    with pytest.raises(ValueError):
        validate_record(record(**changes), IDENTITY, 1000)


def test_closed_marker_identity_includes_boot_and_process_start():
    expected = record()
    assert validate_record(expected, IDENTITY, 1000) == expected


def test_cache_cannot_touch_windows_paths_even_before_validating_root(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    with pytest.raises(OSError, match="Linux script cache is unavailable"):
        PrivateScripts(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_proc_stat_unicode_and_closing_parentheses_do_not_hide_numeric_identity():
    fields = ["S", "1", "42", "42", *["0"] * 15, "12345"]
    assert len(fields) == 20
    assert process_fields("42 (工作 ) task) " + " ".join(fields)) == (1, 42, 42, 12345, "S")
    with pytest.raises(ValueError, match="identity is unavailable"):
        process_fields("not a process stat")
