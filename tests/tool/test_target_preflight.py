from __future__ import annotations

from src.pipeline.capability_library import validate_capability_support
from src.shared.capability import Capability
from src.shared.execution.command_result import CommandResult, CommandStatus
from src.tool.execution_backend import ExecutionBackend
from src.tool.target_preflight import EnvironmentFingerprint, TargetPreflight


class StubBackend(ExecutionBackend):
    def __init__(self, results: list[CommandResult]) -> None:
        self.results = list(results)
        self.calls: list[list[str]] = []

    def run(self, command: list[str], timeout: int = 5) -> CommandResult:
        self.calls.append(command)
        return self.results.pop(0)


def _success(stdout: str) -> CommandResult:
    return CommandResult(status=CommandStatus.SUCCESS, stdout=stdout)


def test_unreachable_target_runs_one_transport_probe_and_caches_failure() -> None:
    backend = StubBackend(
        [CommandResult(status=CommandStatus.SSH_UNREACHABLE, stderr="unreachable")]
    )
    preflight = TargetPreflight(ttl_seconds=30, failure_ttl_seconds=30)

    first = preflight.inspect("dead-ssh", backend)
    second = preflight.inspect("dead-ssh", backend)

    assert first is second
    assert first.reachable is False
    assert first.command_results[0].status is CommandStatus.SSH_UNREACHABLE
    assert backend.calls == [["uname", "-s"]]


def test_preflight_collects_environment_fingerprint() -> None:
    backend = StubBackend(
        [
            _success("Linux"),
            _success('PRETTY_NAME="Debian GNU/Linux 12"'),
            _success("systemd"),
            _success("0"),
            _success("cat\nip\nss\n__PROCFS__\n__SYSFS__"),
        ]
    )

    fingerprint = TargetPreflight().inspect("env-target", backend)

    assert fingerprint.reachable is True
    assert fingerprint.os_family == "linux"
    assert fingerprint.os_name == "Debian GNU/Linux 12"
    assert fingerprint.init_system == "systemd"
    assert fingerprint.privilege_level == "root"
    assert fingerprint.available_binaries == frozenset({"cat", "ip", "ss"})
    assert fingerprint.has_procfs is True
    assert fingerprint.has_sysfs is True


def test_capability_preconditions_fail_before_dispatch() -> None:
    capability = Capability(
        name="get_bandwidth",
        handler=lambda: None,
        preconditions=("linux",),
        required_binaries=("sar",),
        produces_facts=("network.bandwidth",),
    )
    fingerprint = EnvironmentFingerprint(
        target="minimal",
        config_hash="abc",
        reachable=True,
        backend_type="local",
        os_family="linux",
        available_binaries=frozenset({"cat"}),
    )

    decision = validate_capability_support(capability, fingerprint)

    assert decision.supported is False
    assert decision.missing_binaries == ("sar",)
    assert "unsupported" in decision.reason
