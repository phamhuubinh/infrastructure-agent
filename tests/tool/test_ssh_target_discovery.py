from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.tool.execution_backend import SSHExecutionBackend
from src.tool.ssh_target_discovery import discover_ssh_targets
from src.tool.target_registry import TargetRegistry
from src.tool.target_store import TargetStore


class _Completed:
    def __init__(self, stdout: str, returncode: int = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode


def _ssh_config_output(
    *,
    host: str,
    user: str = "ops",
    port: int = 22,
    identity_file: str | None = None,
    strict_host_key_checking: str = "ask",
) -> str:
    lines = [
        f"hostname {host}",
        f"user {user}",
        f"port {port}",
        f"stricthostkeychecking {strict_host_key_checking}",
    ]
    if identity_file is not None:
        lines.append(f"identityfile {identity_file}")
    return "\n".join(lines)


def test_discovers_a_concrete_alias_with_openssh_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "config"
    config.write_text("Host monitor\n    HostName 10.10.10.10\n")
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(command: list[str], **kwargs: object) -> _Completed:
        calls.append((command, kwargs))
        return _Completed(
            _ssh_config_output(
                host="10.10.10.10",
                port=2222,
                identity_file="/private/id_monitor",
            )
        )

    monkeypatch.setattr("src.tool.ssh_target_discovery.subprocess.run", fake_run)

    discovered = discover_ssh_targets(config)

    assert len(discovered) == 1
    target = discovered[0]
    assert target.alias == "monitor"
    assert target.host == "10.10.10.10"
    assert target.user == "ops"
    assert target.port == 2222
    assert target.identity_file == "/private/id_monitor"
    assert target.strict_host_key_checking is True
    assert calls == [
        (
            [
                "ssh",
                "-F",
                str(config),
                "-o",
                "CanonicalizeHostname=no",
                "-G",
                "monitor",
            ],
            {"capture_output": True, "text": True, "timeout": 5, "check": False},
        )
    ]


def test_discovers_multiple_aliases_and_included_configs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "config"
    included = tmp_path / "config.d"
    included.mkdir()
    config.write_text("Include config.d/*\nHost monitor sv1\n")
    (included / "extra.conf").write_text("Host sv2\n")

    def fake_run(command: list[str], **kwargs: object) -> _Completed:
        alias = command[-1]
        return _Completed(_ssh_config_output(host=f"{alias}.internal"))

    monkeypatch.setattr("src.tool.ssh_target_discovery.subprocess.run", fake_run)

    assert [target.alias for target in discover_ssh_targets(config)] == [
        "monitor",
        "sv1",
        "sv2",
    ]


def test_wildcard_aliases_are_not_resolved_or_exposed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "config"
    config.write_text("Host *\nHost *.internal\nHost server-?\nHost monitor\n")
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> _Completed:
        calls.append(command)
        return _Completed(_ssh_config_output(host="10.0.0.20"))

    monkeypatch.setattr("src.tool.ssh_target_discovery.subprocess.run", fake_run)

    assert [target.alias for target in discover_ssh_targets(config)] == ["monitor"]
    assert calls == [
        [
            "ssh",
            "-F",
            str(config),
            "-o",
            "CanonicalizeHostname=no",
            "-G",
            "monitor",
        ]
    ]


def test_missing_config_has_no_discovered_aliases(tmp_path: Path) -> None:
    assert discover_ssh_targets(tmp_path / "missing-config") == ()


def test_host_equals_syntax_discovers_alias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "config"
    config.write_text("Host=monitor\n")
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> _Completed:
        calls.append(command)
        return _Completed(_ssh_config_output(host="10.0.0.20"))

    monkeypatch.setattr("src.tool.ssh_target_discovery.subprocess.run", fake_run)

    assert [target.alias for target in discover_ssh_targets(config)] == ["monitor"]
    assert calls[0][-1] == "monitor"


def test_include_equals_syntax_is_scanned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "config"
    included = tmp_path / "config.d" / "hosts.conf"
    included.parent.mkdir()
    config.write_text("Include=config.d/*\n")
    included.write_text("Host=monitor\n")

    monkeypatch.setattr(
        "src.tool.ssh_target_discovery.subprocess.run",
        lambda *args, **kwargs: _Completed(_ssh_config_output(host="10.0.0.20")),
    )

    assert [target.alias for target in discover_ssh_targets(config)] == ["monitor"]


@pytest.mark.parametrize(
    "match_directive",
    [
        'Match=exec "printf unsafe"',
        'Match !exec "printf unsafe"',
    ],
)
def test_match_exec_spelling_fails_closed_before_subprocess(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    match_directive: str,
) -> None:
    config = tmp_path / "config"
    config.write_text(f"Host=monitor\n{match_directive}\n")

    def unexpected_ssh(*args: object, **kwargs: object) -> _Completed:
        raise AssertionError("Match exec must be rejected before ssh -G")

    monkeypatch.setattr(
        "src.tool.ssh_target_discovery.subprocess.run", unexpected_ssh
    )

    assert discover_ssh_targets(config) == ()


def test_conditional_include_does_not_expose_aliases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "config"
    prod_only = tmp_path / "prod-only.conf"
    config.write_text(f"Host prod\n    Include {prod_only}\n")
    prod_only.write_text("Host secret\n    HostName 10.0.0.9\n")
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> _Completed:
        calls.append(command)
        return _Completed(_ssh_config_output(host="10.0.0.20"))

    monkeypatch.setattr("src.tool.ssh_target_discovery.subprocess.run", fake_run)

    assert [target.alias for target in discover_ssh_targets(config)] == ["prod"]
    assert calls[0][-1] == "prod"


def test_host_negation_excludes_positive_aliases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "config"
    config.write_text("Host monitor !monitor\nHost monitor !mon*\nHost healthy !prod*\n")
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> _Completed:
        calls.append(command)
        return _Completed(_ssh_config_output(host="10.0.0.20"))

    monkeypatch.setattr("src.tool.ssh_target_discovery.subprocess.run", fake_run)

    assert [target.alias for target in discover_ssh_targets(config)] == ["healthy"]
    assert calls[0][-1] == "healthy"


def test_nested_relative_includes_use_the_initial_config_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ssh_dir = tmp_path / ".ssh"
    included_dir = ssh_dir / "includes"
    included_dir.mkdir(parents=True)
    config = ssh_dir / "config"
    config.write_text("Include includes/first.conf\n")
    (included_dir / "first.conf").write_text("Include second.conf\n")
    (ssh_dir / "second.conf").write_text("Host monitor\n")

    monkeypatch.setattr(
        "src.tool.ssh_target_discovery.subprocess.run",
        lambda *args, **kwargs: _Completed(_ssh_config_output(host="10.0.0.20")),
    )

    assert [target.alias for target in discover_ssh_targets(config)] == ["monitor"]


def test_match_exec_skips_discovery_before_ssh_config_evaluation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "config"
    config.write_text('Host monitor\nMatch exec "printf unsafe"\n')

    def unexpected_ssh(*args: object, **kwargs: object) -> _Completed:
        raise AssertionError("ssh -G must not run when Match exec is present")

    monkeypatch.setattr(
        "src.tool.ssh_target_discovery.subprocess.run", unexpected_ssh
    )

    assert discover_ssh_targets(config) == ()


def test_unscannable_include_path_skips_ssh_config_evaluation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "config"
    config.write_text("Include $HOME/ssh-extra.conf\nHost monitor\n")

    def unexpected_ssh(*args: object, **kwargs: object) -> _Completed:
        raise AssertionError("ssh -G must not run for an unscannable Include path")

    monkeypatch.setattr(
        "src.tool.ssh_target_discovery.subprocess.run", unexpected_ssh
    )

    assert discover_ssh_targets(config) == ()


def test_ssh_config_resolution_failure_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "config"
    config.write_text("Host monitor\n")
    monkeypatch.setattr(
        "src.tool.ssh_target_discovery.subprocess.run",
        lambda *args, **kwargs: _Completed("", returncode=255),
    )

    assert discover_ssh_targets(config) == ()


def test_ssh_config_resolution_timeout_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    config = tmp_path / "config"
    config.write_text("Host monitor\n")
    monkeypatch.setattr(
        "src.tool.ssh_target_discovery.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired(cmd="ssh", timeout=5)
        ),
    )

    assert discover_ssh_targets(config) == ()


def test_discovery_never_reads_identity_file_contents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "config"
    identity_file = tmp_path / "id_monitor"
    config.write_text("Host monitor\n")
    identity_file.write_text("private key material")
    original_read_text = Path.read_text
    read_paths: list[Path] = []

    def tracked_read_text(path: Path, *args: object, **kwargs: object) -> str:
        read_paths.append(path)
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", tracked_read_text)
    monkeypatch.setattr(
        "src.tool.ssh_target_discovery.subprocess.run",
        lambda *args, **kwargs: _Completed(
            _ssh_config_output(host="10.0.0.20", identity_file=str(identity_file))
        ),
    )

    discover_ssh_targets(config)

    assert identity_file not in read_paths


def test_registry_integrates_discovered_targets_without_exposing_identity_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "config"
    config.write_text("Host localhost monitor\n")
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> _Completed:
        calls.append(command)
        return _Completed(
            _ssh_config_output(
                host="10.0.0.20",
                identity_file="/private/id_monitor",
                strict_host_key_checking="no",
            )
        )

    monkeypatch.setattr("src.tool.ssh_target_discovery.subprocess.run", fake_run)
    store = TargetStore(
        path=str(tmp_path / "targets.json"),
        discover_ssh_targets_enabled=True,
        ssh_config_path=config,
    )

    registry = TargetRegistry(store=store)

    backend = registry.backend("monitor")
    assert isinstance(backend, SSHExecutionBackend)
    assert backend._identity_file == "/private/id_monitor"
    assert backend._strict_host_key_checking is False
    assert registry.identity("monitor").to_dict() == {
        "name": "monitor",
        "display_name": "monitor",
        "execution_scope": "remote-host",
        "backend_type": "ssh",
        "description": "",
    }
    assert "/private/id_monitor" not in str(registry.identity("monitor").to_dict())
    assert "localhost" in registry.target_names()
    assert registry.identity("localhost").backend_type == "local"
    assert calls == [
        [
            "ssh",
            "-F",
            str(config),
            "-o",
            "CanonicalizeHostname=no",
            "-G",
            "localhost",
        ],
        [
            "ssh",
            "-F",
            str(config),
            "-o",
            "CanonicalizeHostname=no",
            "-G",
            "monitor",
        ],
    ]
    assert registry.get_tool("monitor") is not None
    with pytest.raises(KeyError, match="sv1"):
        registry.get_tool("sv1")


def test_explicit_target_wins_over_discovered_alias(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "config"
    config.write_text("Host monitor\n")
    target_file = tmp_path / "targets.json"
    target_file.write_text(
        json.dumps(
            {
                "targets": {
                    "monitor": {
                        "backend": "ssh",
                        "host": "explicit.example",
                        "user": "admin",
                    }
                }
            }
        )
    )
    monkeypatch.setattr(
        "src.tool.ssh_target_discovery.subprocess.run",
        lambda *args, **kwargs: _Completed(_ssh_config_output(host="discovered.example")),
    )

    registry = TargetRegistry(
        store=TargetStore(
            path=str(target_file),
            discover_ssh_targets_enabled=True,
            ssh_config_path=config,
        )
    )

    backend = registry.backend("monitor")
    assert isinstance(backend, SSHExecutionBackend)
    assert backend._host == "explicit.example"


def test_discovered_targets_are_not_written_to_explicit_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "config"
    config.write_text("Host monitor\n")
    target_file = tmp_path / "targets.json"
    monkeypatch.setattr(
        "src.tool.ssh_target_discovery.subprocess.run",
        lambda *args, **kwargs: _Completed(_ssh_config_output(host="10.0.0.20")),
    )
    registry = TargetRegistry(
        store=TargetStore(
            path=str(target_file),
            discover_ssh_targets_enabled=True,
            ssh_config_path=config,
        )
    )

    registry.add("prod", SSHExecutionBackend(host="10.0.0.30"))

    assert "monitor" not in json.loads(target_file.read_text())["targets"]
