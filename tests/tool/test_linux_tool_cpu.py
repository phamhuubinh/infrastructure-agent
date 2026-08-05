from __future__ import annotations

from src.tool.linux import LinuxTool


def test_cpu_usage_uses_two_proc_stat_snapshots(monkeypatch) -> None:
    snapshots = iter(
        [
            "cpu 100 10 40 800 20 5 5 0 0 0\n",
            "cpu 140 10 60 830 30 5 5 0 0 0\n",
        ]
    )
    calls: list[list[str]] = []

    def run(command, timeout=15):
        calls.append(command)
        if command == ["cat", "/proc/stat"]:
            return True, next(snapshots)
        raise AssertionError(command)

    monkeypatch.setattr("src.tool.linux.capabilities.cpu.time.sleep", lambda _: None)
    tool = LinuxTool()
    tool._run = run

    result = tool.execute({"action": "get_cpu_usage"})

    assert result.success is True
    assert calls == [["cat", "/proc/stat"], ["cat", "/proc/stat"]]
    assert result.data["collection_strategy"] == "proc_stat_delta"
    distribution = sum(
        result.data[key]
        for key in (
            "user_percent",
            "nice_percent",
            "system_percent",
            "idle_percent",
            "iowait_percent",
            "irq_percent",
            "softirq_percent",
            "steal_percent",
        )
    )
    assert abs(distribution - 100.0) <= 0.05
    assert result.data["usage_percent"] == 60.0


def test_cpu_does_not_report_idle_when_distribution_is_unavailable() -> None:
    tool = LinuxTool()
    tool._run = lambda command, timeout=15: (False, "")

    result = tool.execute({"action": "get_cpu_usage"})

    assert result.success is False
    assert result.data is None
