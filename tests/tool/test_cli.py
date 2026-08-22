from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from src.cli.main import _add_target, _remove_target
from src.tool.execution_backend import SSHExecutionBackend
from src.tool.target_registry import TargetRegistry
from src.tool.target_store import TargetStore


def _make_args(
    spec: str,
    target_file: str,
    ssh_user: str = "root",
    ssh_identity_file: str | None = None,
    strict_host_key_checking: bool = True,
) -> argparse.Namespace:
    return argparse.Namespace(
        spec=spec,
        target_file=target_file,
        ssh_user=ssh_user,
        ssh_identity_file=ssh_identity_file,
        strict_host_key_checking=strict_host_key_checking,
    )


def test_add_target_default_strict_host_key_checking(tmp_path: Path) -> None:
    path = str(tmp_path / "targets.json")
    args = _make_args(spec="web@10.0.0.1", target_file=path)
    _add_target(args)

    store = TargetStore(path=path)
    registry = TargetRegistry(store=store)
    backend = registry.backend("web")
    assert isinstance(backend, SSHExecutionBackend)
    assert backend._strict_host_key_checking is True


def test_add_target_can_explicitly_disable_strict_host_key_checking(tmp_path: Path) -> None:
    path = str(tmp_path / "targets.json")
    args = _make_args(
        spec="web@10.0.0.1",
        target_file=path,
        strict_host_key_checking=False,
    )
    _add_target(args)

    store = TargetStore(path=path)
    registry = TargetRegistry(store=store)
    backend = registry.backend("web")
    assert isinstance(backend, SSHExecutionBackend)
    assert backend._strict_host_key_checking is False


def test_remove_target_does_not_discover_runtime_ssh_aliases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def unexpected_discovery(*args: object, **kwargs: object) -> object:
        raise AssertionError("persistent target removal must not run SSH discovery")

    monkeypatch.setattr("src.tool.target_store.discover_ssh_targets", unexpected_discovery)

    with pytest.raises(SystemExit) as exc:
        _remove_target(
            argparse.Namespace(name="monitor", target_file=str(tmp_path / "targets.json"))
        )

    assert exc.value.code == 1
    assert "Target 'monitor' not found." in capsys.readouterr().out
