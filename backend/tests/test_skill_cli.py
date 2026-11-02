"""Offline operator lifecycle needs no running server or model backend."""

import json

import pytest
from test_skill_packages import text

from orion.cli.skills import run_skill_command
from orion.persistence.ownership import RuntimeLease


def test_offline_cli_install_disable_update_enable_remove(tmp_path, monkeypatch, capsys):
    database = tmp_path / "data/orion.db"
    monkeypatch.setenv("ORION_DATABASE_PATH", str(database))
    package = tmp_path / "package"
    package.mkdir()
    (package / "SKILL.md").write_bytes(text())

    def command(*args):
        run_skill_command(list(args))
        return json.loads(capsys.readouterr().out)

    assert command("install", str(package))["skill"]["version"] == "1.0.0"
    command("disable", "fixture-skill")
    (package / "SKILL.md").write_bytes(text().replace(b'"1.0.0"', b'"1.1.0"'))
    assert not command("update", "fixture-skill", str(package))["skill"]["enabled"]
    command("enable", "fixture-skill")
    assert next(s for s in command("list")["skills"] if s["name"] == "fixture-skill")["enabled"]
    command("remove", "fixture-skill")
    assert len(command("list")["skills"]) == 3
    lease = RuntimeLease(database)
    try:
        with pytest.raises(SystemExit, match="stop the active"):
            command("list")
    finally:
        lease.close()
