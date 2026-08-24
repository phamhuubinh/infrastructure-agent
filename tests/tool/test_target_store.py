from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.tool.execution_backend import LocalExecutionBackend, SSHExecutionBackend
from src.tool.target_store import TargetConfigurationError, TargetStore


def test_load_creates_default_local_target_when_file_missing(tmp_path: Path) -> None:
    store = TargetStore(
        path=str(tmp_path / "no_such_file.json"),
        allow_missing_bootstrap=True,
    )
    backends = store.load()

    assert "localhost" in backends
    assert isinstance(backends["localhost"], LocalExecutionBackend)


def test_custom_missing_targets_file_fails_closed(tmp_path: Path) -> None:
    store = TargetStore(
        path=str(tmp_path / "deployment-targets.json"),
    )

    with pytest.raises(TargetConfigurationError, match="does not exist"):
        store.load()


@pytest.mark.parametrize(
    "payload",
    (
        "{not-json",
        json.dumps({"targets": {"prod": None}}),
        json.dumps({"targets": {"prod": {"backend": "typo"}}}),
        json.dumps({"targets": {"prod": {"backend": "ssh", "host": ""}}}),
        json.dumps(
            {"targets": {"prod": {"backend": "ssh", "host": "x", "port": "22"}}}
        ),
    ),
)
def test_malformed_target_authority_never_synthesizes_local_backend(
    tmp_path: Path, payload: str
) -> None:
    path = tmp_path / "deployment-targets.json"
    path.write_text(payload)

    with pytest.raises(TargetConfigurationError):
        TargetStore(path=str(path)).load()


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
    assert data["targets"]["prod"]["strict_host_key_checking"] is True

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


def test_load_legacy_ssh_defaults_host_key_checking_to_enabled(tmp_path: Path) -> None:
    path = tmp_path / "targets.json"
    path.write_text(
        json.dumps(
            {
                "targets": {
                    "staging": {
                        "backend": "ssh",
                        "host": "10.0.0.2",
                    }
                }
            }
        )
    )

    loaded = TargetStore(path=str(path)).load()

    ssh = loaded["staging"]
    assert isinstance(ssh, SSHExecutionBackend)
    assert ssh._strict_host_key_checking is True


def test_save_and_load_strict_host_key_checking(tmp_path: Path) -> None:
    path = str(tmp_path / "targets.json")
    store = TargetStore(path=path)
    store.save(
        {
            "prod": SSHExecutionBackend(
                host="10.0.0.1",
                strict_host_key_checking=True,
            )
        }
    )

    loaded = store.load()

    ssh = loaded["prod"]
    assert isinstance(ssh, SSHExecutionBackend)
    assert ssh._strict_host_key_checking is True


def test_registry_persistence(tmp_path: Path) -> None:
    from src.tool.target_registry import TargetRegistry

    path = str(tmp_path / "targets.json")
    store = TargetStore(path=path)

    registry = TargetRegistry(store=store)
    registry.add(
        "prod",
        SSHExecutionBackend(host="10.0.0.1", user="admin"),
        strict_host_key_checking=True,
    )

    del registry

    reloaded = TargetRegistry(store=store)
    names = reloaded.target_names()
    assert "localhost" in names
    assert "prod" in names
    backend = reloaded.backend("prod")
    assert isinstance(backend, SSHExecutionBackend)
    assert backend._strict_host_key_checking is True


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


def test_target_metadata_loads_explicit_localhost_semantics(tmp_path: Path) -> None:
    path = tmp_path / "targets.json"
    path.write_text(
        json.dumps(
            {
                "targets": {
                    "localhost": {
                        "backend": "local",
                        "display_name": "orion-api",
                        "execution_scope": "orion-runtime",
                        "description": "API container, not physical host",
                    }
                }
            }
        )
    )

    metadata = TargetStore(path=str(path)).load_metadata()

    assert metadata["localhost"]["display_name"] == "orion-api"
    assert metadata["localhost"]["execution_scope"] == "orion-runtime"
