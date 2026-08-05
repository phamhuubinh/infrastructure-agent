from __future__ import annotations

from src.shared.execution.command_result import CommandResult, CommandStatus
from src.tool.capability_result import CapabilityStatus
from src.tool.linux import LinuxTool


def _result(status: CommandStatus, output: str = "") -> CommandResult:
    return CommandResult(
        status=status,
        stdout=output if status in {CommandStatus.SUCCESS, CommandStatus.EMPTY_SUCCESS} else "",
        stderr=output if status not in {CommandStatus.SUCCESS, CommandStatus.EMPTY_SUCCESS} else "",
    )


def test_services_systemd_strategy() -> None:
    tool = LinuxTool()
    tool._run = lambda command, timeout=15: _result(
        CommandStatus.SUCCESS,
        "nginx.service loaded active running nginx",
    )

    result = tool.execute({"action": "get_services"})

    assert result.success is True
    assert result.data["collection_strategy"] == "systemd"
    assert result.data["running"] == 1


def test_services_sysv_fallback_is_partial_alternative_evidence() -> None:
    calls: list[list[str]] = []

    def run(command, timeout=15):
        calls.append(command)
        if command[0] == "systemctl":
            return _result(CommandStatus.COMMAND_NOT_FOUND, "missing")
        return _result(CommandStatus.SUCCESS, " [ + ] nginx\n [ - ] cron")

    tool = LinuxTool()
    tool._run = run
    result = tool.execute({"action": "get_services"})

    assert result.capability_status is CapabilityStatus.PARTIAL
    assert result.data["collection_strategy"] == "sysv"
    assert result.data["confidence"] < 1.0
    assert [call[0] for call in calls] == ["systemctl", "service"]


def test_service_transport_timeout_does_not_run_fallback() -> None:
    calls: list[list[str]] = []

    def run(command, timeout=15):
        calls.append(command)
        return _result(CommandStatus.TIMEOUT, "timeout")

    tool = LinuxTool()
    tool._run = run
    result = tool.execute({"action": "get_service", "name": "nginx"})

    assert result.capability_status is CapabilityStatus.COLLECTION_FAILED
    assert calls == [["systemctl", "is-active", "nginx"]]


def test_process_fallback_never_claims_service_health() -> None:
    def run(command, timeout=15):
        if command[0] in {"systemctl", "service", "rc-service"}:
            return _result(CommandStatus.COMMAND_NOT_FOUND, "missing")
        if command[0] == "pgrep":
            return _result(CommandStatus.SUCCESS, "123\n")
        raise AssertionError(command)

    tool = LinuxTool()
    tool._run = run
    result = tool.execute({"action": "get_service", "name": "nginx"})

    assert result.capability_status is CapabilityStatus.PARTIAL
    assert result.data["process_present"] is True
    assert result.data["health"] == "unknown"
    assert result.data["confidence"] == 0.5


def test_service_logs_are_unit_and_time_bounded() -> None:
    calls: list[list[str]] = []

    def run(command, timeout=15):
        calls.append(command)
        return _result(CommandStatus.SUCCESS, "one\ntwo")

    tool = LinuxTool()
    tool._run = run
    result = tool.execute(
        {
            "action": "get_service_logs",
            "service_name": "nginx",
            "since": 100,
            "until": 200,
            "limit": 20,
        }
    )

    assert result.success is True
    command = calls[0]
    assert command[:3] == ["journalctl", "-u", "nginx.service"]
    assert ["--since", "@100"] == command[command.index("--since") : command.index("--since") + 2]
    assert ["--until", "@200"] == command[command.index("--until") : command.index("--until") + 2]
    assert result.data["entries"] == ["one", "two"]


def test_service_log_parameter_injection_is_rejected_without_command() -> None:
    calls: list[list[str]] = []
    tool = LinuxTool()
    tool._run = lambda command, timeout=15: calls.append(command)

    result = tool.execute(
        {"action": "get_service_logs", "service_name": "nginx;rm -rf /"}
    )

    assert result.capability_status is CapabilityStatus.INVALID_PARAMETERS
    assert calls == []


def test_service_logs_support_last_week_as_a_bounded_range(monkeypatch) -> None:
    fixed_now = 1_786_000_000
    monkeypatch.setattr(
        "src.tool.linux.capabilities.service.time.time", lambda: fixed_now
    )
    calls: list[list[str]] = []

    def run(command, timeout=15):
        calls.append(command)
        return _result(CommandStatus.SUCCESS, "entry")

    tool = LinuxTool()
    tool._run = run
    result = tool.execute(
        {
            "action": "get_service_logs",
            "service_name": "nginx",
            "time_range": "last_week",
        }
    )

    assert result.success is True
    assert result.data["until"] - result.data["since"] + 1 == 7 * 86400
    assert result.data["until"] < fixed_now
    assert "--since" in calls[0]
    assert "--until" in calls[0]


def test_service_logs_reject_wrong_parameter_types_without_command() -> None:
    calls: list[list[str]] = []
    tool = LinuxTool()
    tool._run = lambda command, timeout=15: calls.append(command)

    result = tool.execute(
        {
            "action": "get_service_logs",
            "service_name": "nginx",
            "time_range": 7,
        }
    )

    assert result.capability_status is CapabilityStatus.INVALID_PARAMETERS
    assert calls == []
