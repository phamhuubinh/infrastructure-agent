from __future__ import annotations

import argparse
import io
from pathlib import Path
from unittest import mock

import pytest

from src.cli.main import _manage_model
from src.model.config_store import ModelConfigStore


def test_model_add_reads_secret_from_stdin(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "servers.json"
    monkeypatch.setenv("ORION_SERVERS_FILE", str(config_path))
    monkeypatch.setattr("sys.stdin", io.StringIO("private-key\n"))
    args = argparse.Namespace(
        model_action="add",
        name="primary",
        provider="openai",
        base_url="https://api.openai.com/v1",
        model_name="gpt-4.1",
        api_key="",
        api_key_stdin=True,
        timeout=180,
        temperature=0.0,
        max_tokens=4096,
        no_activate=False,
    )

    _manage_model(args)

    saved = ModelConfigStore(config_path).get("primary")
    assert saved is not None
    assert saved["base_url"] == "https://api.openai.com"
    assert saved["api_key"] == "private-key"
    assert "model test primary" in capsys.readouterr().out


def test_model_test_exits_nonzero_when_connection_fails(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    config_path = tmp_path / "servers.json"
    monkeypatch.setenv("ORION_SERVERS_FILE", str(config_path))
    ModelConfigStore(config_path).upsert(
        "primary", {"base_url": "http://model", "model": "qwen"}
    )
    args = argparse.Namespace(model_action="test", name="primary", timeout=10)

    with (
        mock.patch(
            "src.model.config_store.LLMClient.health_check",
            side_effect=OSError("connection refused"),
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        _manage_model(args)

    assert exc_info.value.code == 1
    assert "Connection failed" in capsys.readouterr().out
