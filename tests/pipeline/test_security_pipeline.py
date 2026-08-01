from __future__ import annotations

from src.pipeline.security.inspector_chain import InspectorChain
from src.pipeline.security.parameter_safety_inspector import ParameterSafetyInspector
from src.pipeline.security.read_only_inspector import ReadOnlyInspector
from src.pipeline.security.target_inspector import TargetInspector
from src.pipeline.security.tool_inspector import (
    InspectionContext,
    InspectionResult,
    InspectionVerdict,
    ToolInspector,
)

# ---------------------------------------------------------------------------
# ToolInspector ABC tests
# ---------------------------------------------------------------------------


def test_inspection_result_allowed() -> None:
    result = InspectionResult(verdict=InspectionVerdict.ALLOW)
    assert result.allowed
    assert not result.denied


def test_inspection_result_denied() -> None:
    result = InspectionResult(
        verdict=InspectionVerdict.DENY,
        reason="test deny",
        inspector_name="TestInspector",
    )
    assert not result.allowed
    assert result.denied
    assert result.reason == "test deny"
    assert result.inspector_name == "TestInspector"


def test_inspection_context_defaults() -> None:
    ctx = InspectionContext()
    assert ctx.capability_name == ""
    assert ctx.target == ""
    assert ctx.resource == ""
    assert ctx.arguments == {}
    assert ctx.tool_name == ""


def test_inspection_context_full() -> None:
    ctx = InspectionContext(
        capability_name="get_cpu",
        target="server01",
        resource="get_cpu",
        arguments={"service_name": "nginx"},
        tool_name="LinuxTool",
    )
    assert ctx.capability_name == "get_cpu"
    assert ctx.target == "server01"
    assert ctx.arguments == {"service_name": "nginx"}
    assert ctx.tool_name == "LinuxTool"


# ---------------------------------------------------------------------------
# ReadOnlyInspector tests
# ---------------------------------------------------------------------------


def test_read_only_allows_get_cpu() -> None:
    inspector = ReadOnlyInspector()
    ctx = InspectionContext(capability_name="get_cpu")
    result = inspector.inspect(ctx)
    assert result.allowed


def test_read_only_allows_list_processes() -> None:
    inspector = ReadOnlyInspector()
    ctx = InspectionContext(capability_name="list_processes")
    result = inspector.inspect(ctx)
    assert result.allowed


def test_read_only_allows_check_memory() -> None:
    inspector = ReadOnlyInspector()
    ctx = InspectionContext(capability_name="check_memory")
    result = inspector.inspect(ctx)
    assert result.allowed


def test_read_only_allows_assess_machine() -> None:
    inspector = ReadOnlyInspector()
    ctx = InspectionContext(capability_name="assess_machine")
    result = inspector.inspect(ctx)
    assert result.allowed


def test_read_only_allows_verify_connection() -> None:
    inspector = ReadOnlyInspector()
    ctx = InspectionContext(capability_name="verify_connection")
    result = inspector.inspect(ctx)
    assert result.allowed


def test_read_only_allows_discover_targets() -> None:
    inspector = ReadOnlyInspector()
    ctx = InspectionContext(capability_name="discover_targets")
    result = inspector.inspect(ctx)
    assert result.allowed


def test_read_only_denies_service_restart() -> None:
    inspector = ReadOnlyInspector()
    ctx = InspectionContext(capability_name="service_restart")
    result = inspector.inspect(ctx)
    assert result.denied
    assert "mutating" in result.reason.lower()


def test_read_only_denies_reboot() -> None:
    inspector = ReadOnlyInspector()
    ctx = InspectionContext(capability_name="reboot")
    result = inspector.inspect(ctx)
    assert result.denied


def test_read_only_denies_shutdown() -> None:
    inspector = ReadOnlyInspector()
    ctx = InspectionContext(capability_name="shutdown")
    result = inspector.inspect(ctx)
    assert result.denied


def test_read_only_denies_process_kill() -> None:
    inspector = ReadOnlyInspector()
    ctx = InspectionContext(capability_name="process_kill")
    result = inspector.inspect(ctx)
    assert result.denied


def test_read_only_denies_file_write() -> None:
    inspector = ReadOnlyInspector()
    ctx = InspectionContext(capability_name="file_write")
    result = inspector.inspect(ctx)
    assert result.denied


def test_read_only_denies_package_install() -> None:
    inspector = ReadOnlyInspector()
    ctx = InspectionContext(capability_name="package_install")
    result = inspector.inspect(ctx)
    assert result.denied


def test_read_only_denies_unknown_capability() -> None:
    inspector = ReadOnlyInspector()
    ctx = InspectionContext(capability_name="weird_custom_thing")
    result = inspector.inspect(ctx)
    assert result.denied
    assert "no explicit read-only classification" in result.reason.lower()


def test_read_only_case_insensitive() -> None:
    inspector = ReadOnlyInspector()
    ctx = InspectionContext(capability_name="SERVICE_RESTART")
    result = inspector.inspect(ctx)
    assert result.denied


# ---------------------------------------------------------------------------
# TargetInspector tests
# ---------------------------------------------------------------------------


def test_target_allow_localhost() -> None:
    inspector = TargetInspector()
    ctx = InspectionContext(target="localhost")
    result = inspector.inspect(ctx)
    assert result.allowed


def test_target_allow_loopback_ip4() -> None:
    inspector = TargetInspector()
    ctx = InspectionContext(target="127.0.0.1")
    result = inspector.inspect(ctx)
    assert result.allowed


def test_target_allow_added_safe() -> None:
    inspector = TargetInspector()
    inspector.add_safe_target("server01")
    ctx = InspectionContext(target="server01")
    result = inspector.inspect(ctx)
    assert result.allowed


def test_target_deny_empty() -> None:
    inspector = TargetInspector()
    ctx = InspectionContext(target="")
    result = inspector.inspect(ctx)
    assert result.denied
    assert "no target" in result.reason.lower()


def test_target_deny_blocked() -> None:
    inspector = TargetInspector(blocked_targets={"prod-server"})
    ctx = InspectionContext(target="prod-server")
    result = inspector.inspect(ctx)
    assert result.denied
    assert "explicitly blocked" in result.reason.lower()


def test_target_blocked_overrides_safe() -> None:
    inspector = TargetInspector(safe_targets={"server01"}, blocked_targets={"server01"})
    ctx = InspectionContext(target="server01")
    result = inspector.inspect(ctx)
    assert result.denied


def test_target_denies_unknown_target() -> None:
    inspector = TargetInspector()
    ctx = InspectionContext(target="some-unknown-server")
    result = inspector.inspect(ctx)
    assert result.denied
    assert "explicit safe list" in result.reason.lower()


def test_target_remove_safe() -> None:
    inspector = TargetInspector(safe_targets={"server01"})
    inspector.remove_safe_target("server01")
    ctx = InspectionContext(target="server01")
    result = inspector.inspect(ctx)
    assert result.denied
    assert "explicit safe list" in result.reason.lower()


def test_target_case_insensitive() -> None:
    inspector = TargetInspector(
        safe_targets={"Server01"}, blocked_targets={"BadServer"}
    )
    assert inspector.inspect(InspectionContext(target="server01")).allowed
    assert inspector.inspect(InspectionContext(target="badserver")).denied


# ---------------------------------------------------------------------------
# ParameterSafetyInspector tests
# ---------------------------------------------------------------------------


def test_param_safety_allows_normal_string() -> None:
    inspector = ParameterSafetyInspector()
    ctx = InspectionContext(arguments={"service_name": "nginx"})
    result = inspector.inspect(ctx)
    assert result.allowed


def test_param_safety_allows_empty_args() -> None:
    inspector = ParameterSafetyInspector()
    ctx = InspectionContext(arguments={})
    result = inspector.inspect(ctx)
    assert result.allowed


def test_param_safety_skips_source_resource_action() -> None:
    inspector = ParameterSafetyInspector()
    ctx = InspectionContext(
        arguments={
            "source": "server01",
            "resource": "get_cpu",
            "action": "get_cpu",
            "extra": "../etc/passwd",
        }
    )
    result = inspector.inspect(ctx)
    assert result.denied
    assert "path traversal" in result.reason.lower()


def test_param_safety_denies_path_traversal() -> None:
    inspector = ParameterSafetyInspector()
    ctx = InspectionContext(arguments={"path": "../../etc/passwd"})
    result = inspector.inspect(ctx)
    assert result.denied
    assert "path traversal" in result.reason.lower()


def test_param_safety_denies_shell_metacharacter() -> None:
    inspector = ParameterSafetyInspector()
    ctx = InspectionContext(arguments={"cmd": "ls; rm -rf /"})
    result = inspector.inspect(ctx)
    assert result.denied
    assert "shell metacharacter" in result.reason.lower()


def test_param_safety_denies_command_substitution() -> None:
    inspector = ParameterSafetyInspector()
    ctx = InspectionContext(arguments={"filter": "$(cat /etc/passwd)"})
    result = inspector.inspect(ctx)
    assert result.denied
    # "$" in "$(cat ...)" matches shell metacharacter pattern first.
    assert "shell metacharacter" in result.reason.lower()


def test_param_safety_denies_backtick() -> None:
    inspector = ParameterSafetyInspector()
    ctx = InspectionContext(arguments={"filter": "`ls -la`"})
    result = inspector.inspect(ctx)
    assert result.denied
    # Backtick char matches shell metacharacter pattern first.
    assert "shell metacharacter" in result.reason.lower()


def test_param_safety_denies_sql_drop() -> None:
    inspector = ParameterSafetyInspector()
    ctx = InspectionContext(arguments={"query": "DROP TABLE users"})
    result = inspector.inspect(ctx)
    assert result.denied
    assert "DROP TABLE" in result.reason


def test_param_safety_denies_sql_delete() -> None:
    inspector = ParameterSafetyInspector()
    ctx = InspectionContext(arguments={"query": "DELETE FROM users"})
    result = inspector.inspect(ctx)
    assert result.denied
    assert "DELETE FROM" in result.reason


def test_param_safety_denies_newline() -> None:
    inspector = ParameterSafetyInspector()
    ctx = InspectionContext(arguments={"comment": "hello\nmalicious"})
    result = inspector.inspect(ctx)
    assert result.denied
    assert "newline" in result.reason.lower()


def test_param_safety_denies_long_parameter() -> None:
    inspector = ParameterSafetyInspector()
    ctx = InspectionContext(arguments={"comment": "x" * 1001})
    result = inspector.inspect(ctx)
    assert result.denied
    assert "maximum length" in result.reason.lower()


def test_param_safety_allows_long_parameter_at_limit() -> None:
    inspector = ParameterSafetyInspector()
    ctx = InspectionContext(arguments={"comment": "x" * 1000})
    result = inspector.inspect(ctx)
    assert result.allowed


def test_param_safety_skips_non_string_values() -> None:
    inspector = ParameterSafetyInspector()
    ctx = InspectionContext(arguments={"count": 42, "enabled": True})
    result = inspector.inspect(ctx)
    assert result.allowed


# ---------------------------------------------------------------------------
# InspectorChain tests
# ---------------------------------------------------------------------------


def test_chain_all_passed() -> None:
    chain = InspectorChain()
    chain.add(ReadOnlyInspector())
    chain.add(ParameterSafetyInspector())
    ctx = InspectionContext(capability_name="get_cpu", arguments={"name": "test"})
    result = chain.inspect(ctx)
    assert result.allowed
    assert result.inspector_name == "InspectorChain"


def test_chain_stops_at_first_deny() -> None:
    chain = InspectorChain()
    chain.add(ReadOnlyInspector())
    chain.add(ParameterSafetyInspector())
    ctx = InspectionContext(
        capability_name="service_restart", arguments={"name": "nginx"}
    )
    result = chain.inspect(ctx)
    assert result.denied
    assert result.inspector_name == "ReadOnlyInspector"


def test_chain_inspect_all() -> None:
    chain = InspectorChain()
    chain.add(ReadOnlyInspector())
    chain.add(ParameterSafetyInspector())
    ctx = InspectionContext(
        capability_name="service_restart", arguments={"comment": "../etc"}
    )
    results = chain.inspect_all(ctx)
    assert len(results) == 2
    assert results[0].denied  # ReadOnly blocks
    assert results[1].denied  # Parameter also blocks


def test_chain_insert() -> None:
    chain = InspectorChain()
    chain.add(ReadOnlyInspector())
    custom = ParameterSafetyInspector()
    chain.insert(0, custom)
    assert chain.inspectors[0].name == "ParameterSafetyInspector"
    assert chain.inspectors[1].name == "ReadOnlyInspector"


def test_chain_remove() -> None:
    chain = InspectorChain()
    chain.add(ReadOnlyInspector())
    chain.add(ParameterSafetyInspector())
    assert chain.remove("ReadOnlyInspector")
    assert not chain.remove("Nonexistent")
    assert len(chain.inspectors) == 1


def test_chain_empty_allows() -> None:
    chain = InspectorChain()
    ctx = InspectionContext(capability_name="anything")
    result = chain.inspect(ctx)
    assert result.allowed


def test_chain_constructor_with_list() -> None:
    inspectors = [ReadOnlyInspector(), ParameterSafetyInspector()]
    chain = InspectorChain(inspectors)
    assert len(chain.inspectors) == 2


class _CustomDenyInspector(ToolInspector):
    @property
    def name(self) -> str:
        return "CustomDenyInspector"

    def inspect(self, context: InspectionContext) -> InspectionResult:
        if context.capability_name == "blocked_cap":
            return InspectionResult(
                verdict=InspectionVerdict.DENY,
                reason="Custom block",
                inspector_name=self.name,
            )
        return InspectionResult(verdict=InspectionVerdict.ALLOW)


def test_custom_inspector() -> None:
    inspector = _CustomDenyInspector()
    ctx = InspectionContext(capability_name="blocked_cap")
    result = inspector.inspect(ctx)
    assert result.denied
    assert result.reason == "Custom block"


def test_chain_with_custom_inspector() -> None:
    chain = InspectorChain([_CustomDenyInspector(), ReadOnlyInspector()])
    ctx = InspectionContext(capability_name="blocked_cap")
    result = chain.inspect(ctx)
    assert result.denied
    assert result.inspector_name == "CustomDenyInspector"


# ---------------------------------------------------------------------------
# Capability mutation_risk field tests
# ---------------------------------------------------------------------------


def test_capability_mutation_risk_default() -> None:
    from src.shared.capability import Capability

    cap = Capability(
        name="list_cpu",
        handler=lambda: {"cpu": 50},
    )
    assert cap.mutation_risk == "none"


def test_capability_mutation_risk_explicit() -> None:
    from src.shared.capability import Capability

    cap = Capability(
        name="service_restart",
        handler=lambda svc: {"status": "restarted"},
        mutation_risk="high",
    )
    assert cap.mutation_risk == "high"
