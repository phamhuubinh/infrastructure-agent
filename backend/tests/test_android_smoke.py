"""Android smoke recovery only retries safe ADB operations."""

from __future__ import annotations

import runpy
import subprocess
import time
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET

import pytest


@pytest.fixture
def smoke(monkeypatch):
    path = Path(__file__).resolve().parents[2] / "scripts/android/smoke.py"
    module = runpy.run_path(str(path))
    monkeypatch.setitem(
        module["Emulator"].run.__globals__,
        "time",
        SimpleNamespace(sleep=lambda _: None, monotonic=time.monotonic),
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


@pytest.mark.parametrize(
    "interrupted_stdout", ["", "Current Input Method Manager state:\nmInputShown=false\n"]
)
def test_ime_probe_retries_after_transport_recovers(smoke, monkeypatch, interrupted_stdout):
    emulator = smoke.Emulator("adb", "emulator-5554")
    calls = fake_adb(
        monkeypatch,
        emulator,
        [
            (255, interrupted_stdout, ""),
            (1, "", "adb: device offline"),
            (0, "device\n", ""),
            (0, "mInputShown=true", ""),
        ],
    )
    assert smoke.Ui(emulator).keyboard_visible()
    assert calls == [calls[0], ("get-state",), ("get-state",), calls[0]]


def test_ime_probe_fails_if_retry_also_returns_partial_stdout(smoke, monkeypatch):
    emulator = smoke.Emulator("adb", "emulator-5554")
    partial = (255, "Current Input Method Manager state:\nmInputShown=true\n", "")
    calls = fake_adb(monkeypatch, emulator, [partial, (0, "device\n", ""), partial])
    with pytest.raises(smoke.AdbConnectionError, match="exit 255"):
        smoke.Ui(emulator).keyboard_visible()
    assert calls == [calls[0], ("get-state",), calls[0]]


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


def test_enrollment_scrolls_to_real_button_before_tapping(smoke, monkeypatch):
    emulator = smoke.Emulator("adb", "emulator-5554")
    calls = fake_adb(
        monkeypatch, emulator, [(0, "Physical size: 320x640", ""), (0, "", ""), (0, "", "")]
    )
    ui = smoke.Ui(emulator)
    name = "Kết nối bằng mã"
    snapshots = iter(
        [
            [ET.Element("node", text=name, bounds=bounds)]
            for bounds in ("[0,0][0,0]", "[40,500][120,540]")
        ]
    )
    monkeypatch.setattr(ui, "nodes", lambda *args, **kwargs: next(snapshots))

    ui.click(name, reveal=True)

    assert calls == [
        ("shell", "wm", "size"),
        ("shell", "input", "swipe", "160", "480", "160", "213", "350"),
        ("shell", "input", "tap", "80", "520"),
    ]


def test_file_picker_chooses_drawer_row_instead_of_matching_breadcrumb(smoke, monkeypatch):
    ui = smoke.Ui(smoke.Emulator("adb", "emulator-5554"))
    name = "sdk_gphone64_x86_64"
    breadcrumb = ET.Element("node", {"text": name, "resource-id": "picker:id/breadcrumb_text"})
    drawer = ET.Element("node", {"text": name, "resource-id": "android:id/title"})
    monkeypatch.setattr(ui, "nodes", lambda *args, **kwargs: [breadcrumb, drawer])

    assert ui.find(name, package="picker", resource_id="android:id/title") is drawer
