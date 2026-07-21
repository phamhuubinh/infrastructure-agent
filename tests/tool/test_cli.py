from __future__ import annotations

import argparse
from pathlib import Path

from src.cli.main import _add_target
from src.tool.execution_backend import SSHExecutionBackend
from src.tool.target_registry import TargetRegistry
from src.tool.target_store import TargetStore


def _make_args(
    spec: str,
    target_file: str,
    ssh_user: str = "root",
    ssh_identity_file: str | None = None,
    strict_host_key_checking: bool = False,
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
    assert backend._strict_host_key_checking is False


def test_add_target_with_strict_host_key_checking(tmp_path: Path) -> None:
    path = str(tmp_path / "targets.json")
    args = _make_args(
        spec="web@10.0.0.1",
        target_file=path,
        strict_host_key_checking=True,
    )
    _add_target(args)

    store = TargetStore(path=path)
    registry = TargetRegistry(store=store)
    backend = registry.backend("web")
    assert isinstance(backend, SSHExecutionBackend)
    assert backend._strict_host_key_checking is True
