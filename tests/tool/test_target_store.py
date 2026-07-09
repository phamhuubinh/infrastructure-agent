from __future__ import annotations

import json
from pathlib import Path

from src.tool.execution_backend import LocalExecutionBackend, SSHExecutionBackend
from src.tool.target_store import TargetStore


def test_load_creates_default_local_target_when_file_missing(tmp_path: Path) -> None:
    store = TargetStore(path=str(tmp_path / "no_such_file.json"))
    backends = store.load()

    assert "localhost" in backends
    assert isinstance(backends["localhost"], LocalExecutionBackend)


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    path = str(tmp_path / "targets.json")
    store = TargetStore(path=path)

    backends = {
        "localhost": LocalExecutionBackend(),
        "prod": SSHExecutionBackend(
            host="10.0.0.1",
            user="admin",
            port=2222,
            identity_file="/root/.ssh/id_rsa",
        ),
    }
    store.save(backends)

    raw = Path(path).read_text()
    data = json.loads(raw)
    assert data["targets"]["localhost"] == {"backend": "local"}
    assert data["targets"]["prod"]["backend"] == "ssh"
    assert data["targets"]["prod"]["host"] == "10.0.0.1"
    assert data["targets"]["prod"]["port"] == 2222
    assert data["targets"]["prod"]["user"] == "admin"
    assert data["targets"]["prod"]["identity_file"] == "/root/.ssh/id_rsa"

    loaded = store.load()
    assert isinstance(loaded["localhost"], LocalExecutionBackend)
    assert isinstance(loaded["prod"], SSHExecutionBackend)


def test_save_and_load_minimal_ssh(tmp_path: Path) -> None:
    path = str(tmp_path / "targets.json")
    store = TargetStore(path=path)

    backends = {
        "staging": SSHExecutionBackend(host="10.0.0.2"),
    }
    store.save(backends)

    loaded = store.load()
    ssh = loaded["staging"]
    assert isinstance(ssh, SSHExecutionBackend)
    assert ssh._host == "10.0.0.2"
    assert ssh._port == 22
    assert ssh._user == "root"
    assert ssh._identity_file is None


def test_registry_persistence(tmp_path: Path) -> None:
    from src.tool.target_registry import TargetRegistry

    path = str(tmp_path / "targets.json")
    store = TargetStore(path=path)

    registry = TargetRegistry(store=store)
    registry.add("prod", SSHExecutionBackend(host="10.0.0.1", user="admin"))

    del registry

    reloaded = TargetRegistry(store=store)
    names = reloaded.target_names()
    assert "localhost" in names
    assert "prod" in names


def test_registry_remove_persists(tmp_path: Path) -> None:
    from src.tool.target_registry import TargetRegistry

    path = str(tmp_path / "targets.json")
    store = TargetStore(path=path)

    registry = TargetRegistry(store=store)
    registry.add("prod", SSHExecutionBackend(host="10.0.0.1"))
    registry.remove("prod")

    del registry

    reloaded = TargetRegistry(store=store)
    assert "prod" not in reloaded.target_names()
