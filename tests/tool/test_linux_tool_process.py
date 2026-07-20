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
        "12345  /sbin/init 0.5  /sbin/init -x\n"
        "67890  /usr/bin/python3 1.2  python3 script.py\n"
        "11111  0.0  0.1  systemd --user\n"
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
        "PID  CPU  MEM  CMD\n"
        "1  0.0  0.1  init\n"
        "2  5.5  2.0  python\n"
        "3  N/A  1.0  weird_process\n"
        "4  3.2  NaN  another_weird\n"
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
        "1  0.0  0.1  init\n"
        "100  12.5  3.2  python app.py\n"
        "200  8.0  1.5  nginx -g daemon off\n"
    )
    tool = LinuxTool(backend=backend)
    result = tool.execute({"action": "get_process"})
    assert result.success
    assert result.data["total"] == 3
    top_cpu = result.data["top_cpu"]
    assert len(top_cpu) > 0
    assert float(top_cpu[0]["cpu_percent"]) >= 0
