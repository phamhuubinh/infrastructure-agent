"""Administrative SSH target/argv fixtures, without accessing a live account."""

from __future__ import annotations

import json
import os

import pytest

from orion.integrations.ssh.config import (
    REMOTE_BOOTSTRAP,
    SSHConfigurationError,
    load_configuration,
    ssh_argv,
)


def configuration(tmp_path, **overrides):
    return {
        "format_version": 1,
        "targets": [
            {
                "target_ref": "ssh:lab",
                "ssh_alias": "lab-alias",
                "commands": True,
                "config_file": str(tmp_path / "private folder" / "config"),
                "known_hosts_file": str(tmp_path / "private folder" / "known_hosts"),
                **overrides,
            }
        ],
    }


def write(tmp_path, data):
    path = tmp_path / "targets.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_unset_ssh_commands_never_discovers_workstation_or_legacy_targets(monkeypatch):
    monkeypatch.delenv("ORION_SSH_COMMAND_CONFIG", raising=False)
    monkeypatch.setenv("ORION_SSH_TARGET_REFS", "legacy-monitor")
    assert load_configuration().targets == ()


@pytest.mark.parametrize(
    "override",
    [
        {"target_ref": "lab"},
        {"ssh_alias": "-oProxyCommand=bad"},
        {"ssh_alias": "lab; echo bad"},
        {"ssh_alias": "lab\nother"},
        {"commands": "true"},
        {"identity_file": "model-selected"},
        {"config_file": "relative/config"},
        {"known_hosts_file": "bad\npath"},
        {"known_hosts_file": "/private/%h-hosts"},
        {"known_hosts_file": "/private/${HOME}"},
    ],
)
def test_closed_configuration_rejects_ambiguous_or_model_connection_material(tmp_path, override):
    with pytest.raises(SSHConfigurationError) as error:
        load_configuration(write(tmp_path, configuration(tmp_path, **override)))
    assert str(error.value) == "SSH command configuration is unavailable."
    assert error.value.__cause__ is None


def test_duplicate_oversized_and_linked_configuration_fail_closed(tmp_path):
    data = configuration(tmp_path)
    data["targets"] *= 2
    with pytest.raises(SSHConfigurationError):
        load_configuration(write(tmp_path, data))
    path = write(tmp_path, {})
    path.write_bytes(b" " * 65_537)
    with pytest.raises(SSHConfigurationError):
        load_configuration(path)
    path.write_text(json.dumps(configuration(tmp_path)))
    linked = tmp_path / "alias.json"
    os.link(path, linked)
    with pytest.raises(SSHConfigurationError):
        load_configuration(linked)


def test_default_disabled_and_strict_argv_keep_paths_as_data(tmp_path):
    disabled = configuration(tmp_path)
    del disabled["targets"][0]["commands"]
    config = load_configuration(write(tmp_path, disabled))
    assert config.enabled_target("ssh:lab") is None
    with pytest.raises(PermissionError):
        ssh_argv(config.targets[0], str(tmp_path / "ssh.exe"))
    config = load_configuration(write(tmp_path, configuration(tmp_path)))
    target = config.enabled_target("ssh:lab")
    assert target is not None and config.enabled_target("ssh:other") is None
    executable = str(tmp_path / "Open SSH" / "ssh.exe")
    argv = ssh_argv(target, executable)
    assert argv[:4] == [executable, "-T", "-F", target.config_file]
    assert argv[-3:] == ["--", "lab-alias", REMOTE_BOOTSTRAP]
    assert "StrictHostKeyChecking=yes" in argv and "BatchMode=yes" in argv
    assert "ForwardAgent=no" in argv and "ControlPath=none" in argv
    assert 'UserKnownHostsFile="' + target.known_hosts_file.replace("\\", "/") + '"' in argv
    assert "lab-alias" not in repr(target)
    assert target.config_file not in repr(target)
    with pytest.raises(ValueError):
        ssh_argv(target, "ssh")
