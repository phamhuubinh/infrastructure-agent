from __future__ import annotations

from src.discovery.linux import updater


def test_run_invokes_subprocess_with_given_command(monkeypatch, capsys) -> None:
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

    monkeypatch.setattr(updater.subprocess, "run", fake_run)

    updater.run(["echo", "hello"])

    assert calls == [["echo", "hello"]]

    captured = capsys.readouterr()
    assert "echo hello" in captured.out


def test_main_runs_collector_then_transformer(monkeypatch) -> None:
    calls = []

    def fake_run(cmd):
        calls.append(cmd)

    monkeypatch.setattr(updater, "run", fake_run)

    updater.main()

    assert len(calls) == 2

    collector_cmd = calls[0]
    transformer_cmd = calls[1]

    assert collector_cmd[1].endswith("collector.py")
    assert collector_cmd[2] == "-o"
    assert collector_cmd[3] == str(updater.RAW)

    assert transformer_cmd[1].endswith("transformer.py")
    assert transformer_cmd[2] == str(updater.RAW)
    assert transformer_cmd[3] == "-o"
    assert transformer_cmd[4] == str(updater.INVENTORY)


def test_raw_and_inventory_paths_are_under_stable_store() -> None:
    assert updater.RAW.parts[-4:] == ("stable_store", "linux", "raw", "osquery.json")
    assert updater.INVENTORY.parts[-3:] == ("stable_store", "linux", "inventory.json")
