from __future__ import annotations

from src.tool.execution_backend import ExecutionBackend
from src.tool.linux_tool import LinuxTool


class _MockBackend(ExecutionBackend):
    """Backend that returns controlled ps output for process tests."""

    def __init__(self, ps_output: str):
        self._ps_output = ps_output
        self.call_count = 0

    def run(self, command: list[str], timeout: int = 5) -> tuple[bool, str]:
        self.call_count += 1
        cmd = " ".join(command)
        if "ps" in cmd:
            return (True, self._ps_output)
        if "cat" in cmd or "nproc" in cmd or "top" in cmd:
            return (True, "0" if "nproc" in cmd else "")
        if "free" in cmd:
            return (True, "MemTotal: 16000000 kB\nMemAvailable: 8000000 kB")
        return (True, "")


def test_get_process_with_malformed_cpu_percent() -> None:
    """ps output where cpu_percent field is non-numeric (e.g. a command name).

    Previously this would crash with ValueError in float().
    """
    backend = _MockBackend(
        "12345  S  /sbin/init 0.5  /sbin/init -x\n"
        "67890  S  /usr/bin/python3 1.2  python3 script.py\n"
        "11111  S  0.0  0.1  systemd --user\n"
    )
    tool = LinuxTool(backend=backend)
    result = tool.execute({"action": "get_process"})
    assert result.success
    assert "total" in result.data
    assert result.data["total"] == 3
    assert "top_cpu" in result.data
    assert "top_memory" in result.data


def test_get_process_with_partial_malformed_data() -> None:
    """Mix of valid and invalid cpu_percent values — should not crash."""
    backend = _MockBackend(
        "PID  STAT  CPU  MEM  CMD\n"
        "1  S  0.0  0.1  init\n"
        "2  S  5.5  2.0  python\n"
        "3  Z  N/A  1.0  weird_process\n"
        "4  S  3.2  NaN  another_weird\n"
    )
    tool = LinuxTool(backend=backend)
    result = tool.execute({"action": "get_process"})
    assert result.success
    assert "top_cpu" in result.data
    assert "top_memory" in result.data


def test_get_process_handles_empty_output() -> None:
    """Empty ps output should produce empty process lists."""
    backend = _MockBackend("")
    tool = LinuxTool(backend=backend)
    result = tool.execute({"action": "get_process"})
    assert result.success
    assert result.data["total"] == 0
    assert result.data["summary"] == "0 running processes"


def test_get_process_with_valid_data() -> None:
    """Normal valid data should still work correctly (regression check)."""
    backend = _MockBackend(
        "1  S  0.0  0.1  init\n"
        "100  S  12.5  3.2  python app.py\n"
        "200  S  8.0  1.5  nginx -g daemon off\n"
    )
    tool = LinuxTool(backend=backend)
    result = tool.execute({"action": "get_process"})
    assert result.success
    assert result.data["total"] == 3
    top_cpu = result.data["top_cpu"]
    assert len(top_cpu) > 0
    assert float(top_cpu[0]["cpu_percent"]) >= 0


def test_zombie_detection_uses_process_state_not_command_text() -> None:
    """GA2-G03: a process whose command line says 'zombie' but STAT is S is
    NOT a zombie; a process with STAT Z IS a zombie even if its command
    line omits the word."""
    backend = _MockBackend(
        "1  S  0.0  0.1  init\n"
        "2  Z  0.0  0.0  [python] <defunct>\n"
        "3  S  0.0  0.0  zombie-looking-cmd\n"
        "4  Z  0.0  0.0  [nginx] <defunct>\n"
    )
    tool = LinuxTool(backend=backend)
    result = tool.execute({"action": "get_process"})
    assert result.success
    # Only the processes whose STAT contains Z count as zombies.
    assert result.data["zombie_count"] == 2
    assert "zombie-looking-cmd" not in result.data["zombie_processes"]


def test_zombie_failure_returns_no_fabricated_zero() -> None:
    """A failed ps probe must not fabricate a zero zombie count."""
    backend = _MockBackend("")
    tool = LinuxTool(backend=backend)
    result = tool.execute({"action": "get_process"})
    assert result.success
    assert "zombie_count" in result.data
    assert result.data["zombie_count"] == 0
