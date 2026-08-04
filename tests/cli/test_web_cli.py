from __future__ import annotations

import argparse
import importlib
import sys
from unittest import mock

from src.cli.main import _run_web_command

cli_main = importlib.import_module("src.cli.main")


def _args() -> argparse.Namespace:
    return argparse.Namespace(
        port=61888,
        target_file="targets.json",
        server=None,
        model=None,
    )


def test_packaged_web_command_reports_existing_ui(monkeypatch, capsys) -> None:
    monkeypatch.setenv("ORION_PACKAGED_WEB_URL", "http://localhost")
    with mock.patch.object(cli_main, "run_web") as run_web:
        _run_web_command(_args())

    run_web.assert_not_called()
    assert "already running at http://localhost" in capsys.readouterr().out


def test_native_web_command_starts_local_web(monkeypatch) -> None:
    monkeypatch.delenv("ORION_PACKAGED_WEB_URL", raising=False)
    with mock.patch.object(cli_main, "run_web") as run_web:
        _run_web_command(_args())

    run_web.assert_called_once_with(
        port=61888,
        target_store_path="targets.json",
        server_name=None,
        model=None,
    )


def test_packaged_help_describes_launcher_lifecycle(monkeypatch, capsys) -> None:
    monkeypatch.setenv("ORION_PACKAGED_WEB_URL", "http://localhost")
    monkeypatch.setattr(sys, "argv", ["orion", "help"])

    cli_main.main()

    output = capsys.readouterr().out
    assert "Start packaged Web UI and follow Web logs" in output
    assert "Stop API, UI, and reverse proxy" in output
    assert "Follow logs from every Compose service" in output
    assert "Exit logs; keep Orion running" in output
