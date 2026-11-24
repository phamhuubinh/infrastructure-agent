"""Android smoke recovery only retries safe ADB operations."""

from __future__ import annotations

import runpy
import subprocess
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def smoke(monkeypatch):
    path = Path(__file__).resolve().parents[2] / "scripts/android/smoke.py"
    module = runpy.run_path(str(path))
    monkeypatch.setitem(
        module["Emulator"].run.__globals__, "time", SimpleNamespace(sleep=lambda _: None)
    )
    return SimpleNamespace(**module)


def fake_adb(monkeypatch, emulator, responses):
    calls = []
    outcomes = iter(responses)

    def call(args, timeout):
        calls.append(args)
        return subprocess.CompletedProcess(args, *next(outcomes))

    monkeypatch.setattr(emulator, "_call", call)
    return calls


def test_ime_probe_retries_after_transport_recovers(smoke, monkeypatch):
    emulator = smoke.Emulator("adb", "emulator-5554")
    calls = fake_adb(
        monkeypatch,
        emulator,
        [
            (255, "", ""),
            (1, "", "adb: device offline"),
            (0, "device\n", ""),
            (0, "mInputShown=true", ""),
        ],
    )
    assert smoke.Ui(emulator).keyboard_visible()
    assert calls == [calls[0], ("get-state",), ("get-state",), calls[0]]


def test_disconnected_emulator_fails_after_bounded_polls(smoke, monkeypatch):
    emulator = smoke.Emulator("adb", "emulator-5554")
    offline = (1, "", "adb: device offline")
    calls = fake_adb(monkeypatch, emulator, [offline] * 5)
    with pytest.raises(smoke.AdbConnectionError, match="device offline"):
        smoke.Ui(emulator).keyboard_visible()
    assert calls[1:] == [("get-state",)] * 4


def test_application_error_and_mutating_input_are_not_replayed(smoke, monkeypatch):
    emulator = smoke.Emulator("adb", "emulator-5554")
    calls = fake_adb(
        monkeypatch, emulator, [(1, "", "Cannot find service: input_method"), (255, "", "")]
    )
    with pytest.raises(RuntimeError, match="Cannot find service"):
        smoke.Ui(emulator).keyboard_visible()
    with pytest.raises(smoke.AdbConnectionError):
        emulator.run("shell", "input", "text", "test")
    assert calls == [("shell", "dumpsys", "input_method"), ("shell", "input", "text", "test")]


def test_cleanup_preserves_assertion_and_fails_when_only_cleanup_fails(smoke, monkeypatch):
    emulator = smoke.Emulator("adb", "emulator-5554")
    fake_adb(monkeypatch, emulator, [(1, "", "cleanup failed")] * 2)
    with pytest.raises(AssertionError, match="application assertion"), ExitStack() as stack:
        emulator.cleanup(stack, "uninstall", smoke.PACKAGE)
        raise AssertionError("application assertion")
    with pytest.raises(RuntimeError, match="cleanup failed"), ExitStack() as stack:
        emulator.cleanup(stack, "uninstall", smoke.PACKAGE)
