from __future__ import annotations

import inspect

import pytest

from src.agent.controller_contracts import AgentAction
from src.pipeline.agent_action_executor import (
    AgentActionExecutionReason,
    AgentActionExecutionResult,
    AgentActionExecutionStatus,
    AgentActionExecutor,
)
from src.pipeline.agent_action_validator import (
    AgentActionToolBudget,
    AgentActionValidationReason,
    AgentActionValidationResult,
    AgentActionValidationStatus,
    AgentActionValidator,
)
from src.pipeline.controller_capability_discovery import ControllerCapabilityDiscovery
from src.pipeline.hard_request_constraints import (
    HardRequestConstraints,
    HardTargetReference,
)
from src.pipeline.target_resolver import TargetResolver
from src.shared.execution.tool_result import ToolResult
from src.tool.capability_result import CapabilityStatus
from src.tool.grafana_tool import GrafanaTool
from src.tool.knowledge_tool import KnowledgeTool
from src.tool.target_registry import TargetRegistry
from tests.fixtures.fake_environment import (
    FAKE_GRAFANA_URL,
    FAKE_TOOL_TOKEN,
    fake_environment,
)


def _valid_host_result() -> tuple[object, AgentActionValidationResult]:
    environment = fake_environment()
    validator = AgentActionValidator(
        ControllerCapabilityDiscovery.from_knowledge_tool(environment.knowledge_tool),
        environment.target_resolver,
    )
    validation = validator.validate(
        AgentAction("host.get_listening_ports", {"port": 443}),
        HardRequestConstraints(
            explicit_target=HardTargetReference("localhost", "localhost")
        ),
        AgentActionToolBudget(),
    )
    assert validation.status is AgentActionValidationStatus.VALID
    return environment, validation


def test_valid_host_action_dispatches_once_with_exact_target_and_inspectors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment, validation = _valid_host_result()
    captured: list[dict[str, object]] = []

    def execute(_self: object, arguments: dict[str, object]) -> ToolResult:
        captured.append(dict(arguments))
        return ToolResult(success=True, data={"ports": [443]})

    monkeypatch.setattr("src.tool.linux_tool.LinuxTool.execute", execute)

    result = AgentActionExecutor(environment.knowledge_tool).execute(
        validation, AgentActionToolBudget(max_actions=2, max_tools=2)
    )

    assert captured == [{"action": "get_listening_ports", "port": 443}]
    assert result.status is AgentActionExecutionStatus.SUCCESS
    assert result.reason is AgentActionExecutionReason.DISPATCHED
    assert result.source_id == result.target_id == "localhost"
    assert result.tool_result is not None
    assert result.tool_result.security_inspected is True
    assert result.tool_result.security_allowed is True
    assert result.evidence is not None
    assert result.evidence.source == "localhost"
    assert result.budget.actions_used == result.budget.tools_used == 1


def test_host_action_preserves_a_validated_remote_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.tool.target_preflight import EnvironmentFingerprint

    environment = fake_environment(ssh=True)
    monkeypatch.setattr(
        environment.registry,
        "preflight",
        lambda target: EnvironmentFingerprint(
            target=target,
            config_hash="fixture",
            reachable=True,
            backend_type="ssh",
            os_family="linux",
            available_binaries=frozenset({"ss", "ps"}),
        ),
    )
    validator = AgentActionValidator(
        ControllerCapabilityDiscovery.from_knowledge_tool(environment.knowledge_tool),
        environment.target_resolver,
    )
    validation = validator.validate(
        AgentAction("host.get_listening_ports", {"port": 443}),
        HardRequestConstraints(
            explicit_target=HardTargetReference("remote-1", "remote-1")
        ),
        AgentActionToolBudget(),
    )
    captured: list[dict[str, object]] = []

    def execute(_self: object, arguments: dict[str, object]) -> ToolResult:
        captured.append(dict(arguments))
        return ToolResult(success=True, data={"ports": [443]})

    monkeypatch.setattr("src.tool.linux_tool.LinuxTool.execute", execute)

    result = AgentActionExecutor(environment.knowledge_tool).execute(
        validation, AgentActionToolBudget()
    )

    assert validation.status is AgentActionValidationStatus.VALID
    assert captured == [{"action": "get_listening_ports", "port": 443}]
    assert result.target_id == result.source_id == "remote-1"
    assert result.tool_result is not None
    assert result.tool_result.source == "remote-1"


def test_non_valid_or_exhausted_action_never_reaches_knowledge_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment, validation = _valid_host_result()
    calls = 0

    def execute(_arguments: dict[str, object]) -> ToolResult:
        nonlocal calls
        calls += 1
        return ToolResult(success=True)

    monkeypatch.setattr(environment.knowledge_tool, "execute", execute)
    executor = AgentActionExecutor(environment.knowledge_tool)
    rejected = AgentActionValidationResult(
        AgentActionValidationStatus.REJECT,
        AgentActionValidationReason.CAPABILITY_UNKNOWN,
        "host.get_listening_ports",
    )

    rejected_result = executor.execute(rejected, AgentActionToolBudget())
    exhausted_result = executor.execute(
        validation,
        AgentActionToolBudget(max_actions=1, actions_used=1),
    )

    assert calls == 0
    assert rejected_result.reason is AgentActionExecutionReason.VALIDATION_NOT_VALID
    assert exhausted_result.reason is AgentActionExecutionReason.BUDGET_EXHAUSTED
    assert rejected_result.budget.actions_used == 0
    assert exhausted_result.budget.actions_used == 1


def test_failure_and_partial_result_preserve_typed_outcomes_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment, validation = _valid_host_result()
    calls = 0

    def failed_execute(_self: object, _arguments: dict[str, object]) -> ToolResult:
        nonlocal calls
        calls += 1
        return ToolResult(
            success=False,
            error="transport unavailable",
            capability_status=CapabilityStatus.COLLECTION_FAILED,
        )

    monkeypatch.setattr("src.tool.linux_tool.LinuxTool.execute", failed_execute)
    failed = AgentActionExecutor(environment.knowledge_tool).execute(
        validation, AgentActionToolBudget()
    )

    assert calls == 1
    assert failed.status is AgentActionExecutionStatus.FAILURE
    assert failed.tool_result is not None
    assert failed.tool_result.capability_status is CapabilityStatus.COLLECTION_FAILED
    assert failed.evidence is not None
    assert failed.evidence.success is False
    assert failed.budget.actions_used == failed.budget.tools_used == 1

    def partial_execute(_self: object, _arguments: dict[str, object]) -> ToolResult:
        return ToolResult(
            success=False,
            data={"ports": [443]},
            error="one collector failed",
            capability_status=CapabilityStatus.PARTIAL,
        )

    monkeypatch.setattr("src.tool.linux_tool.LinuxTool.execute", partial_execute)
    partial = AgentActionExecutor(environment.knowledge_tool).execute(
        validation, AgentActionToolBudget()
    )

    assert partial.status is AgentActionExecutionStatus.PARTIAL
    assert partial.evidence is not None
    assert partial.evidence.status is CapabilityStatus.PARTIAL
    assert partial.evidence.success is False
    assert partial.evidence.data == {"ports": [443]}


def test_dispatch_preserves_tool_result_schema_version_for_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment, validation = _valid_host_result()

    def execute(_self: object, _arguments: dict[str, object]) -> ToolResult:
        return ToolResult(
            success=True,
            data={"ports": [443]},
            schema_version="sentinel-v7",
        )

    monkeypatch.setattr("src.tool.linux_tool.LinuxTool.execute", execute)
    result = AgentActionExecutor(environment.knowledge_tool).execute(
        validation, AgentActionToolBudget()
    )

    assert result.tool_result is not None
    assert result.tool_result.schema_version == "sentinel-v7"
    assert result.evidence is not None
    assert result.evidence.schema_version == "sentinel-v7"


@pytest.mark.parametrize(
    ("family", "capability_id", "resource"),
    (
        ("grafana", "grafana.dashboards", "dashboards"),
        ("zabbix", "zabbix.get_hosts", "get_hosts"),
        ("internet", "internet.web_search", "web_search"),
    ),
)
def test_source_backed_actions_keep_the_canonical_source_identity(
    monkeypatch: pytest.MonkeyPatch,
    family: str,
    capability_id: str,
    resource: str,
) -> None:
    environment = fake_environment(**{family: True})
    validator = AgentActionValidator(
        ControllerCapabilityDiscovery.from_knowledge_tool(environment.knowledge_tool),
        environment.target_resolver,
    )
    arguments = {"query": "Orion"} if family == "internet" else {}
    validation = validator.validate(
        AgentAction(capability_id, arguments),
        HardRequestConstraints(),
        AgentActionToolBudget(),
    )
    assert validation.status is AgentActionValidationStatus.VALID
    assert validation.source_id == family
    captured: list[dict[str, object]] = []

    def execute(_self: object, arguments: dict[str, object]) -> ToolResult:
        captured.append(dict(arguments))
        return ToolResult(success=True, data={"ok": True})

    tool_path = {
        "grafana": "src.tool.grafana_tool.GrafanaTool.execute",
        "zabbix": "src.tool.zabbix_tool.ZabbixTool.execute",
        "internet": "src.tool.internet_tool.InternetTool.execute",
    }[family]
    monkeypatch.setattr(tool_path, execute)

    result = AgentActionExecutor(environment.knowledge_tool).execute(
        validation, AgentActionToolBudget()
    )

    assert result.source_id == family
    assert result.tool_result is not None
    assert result.tool_result.source == family
    assert captured == [{"action": resource, **arguments}]


def test_ambiguous_source_backed_capability_fails_before_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = TargetRegistry()
    registry.register_tool(
        "grafana-a", GrafanaTool(url=FAKE_GRAFANA_URL, token=FAKE_TOOL_TOKEN)
    )
    registry.register_tool(
        "grafana-b", GrafanaTool(url=FAKE_GRAFANA_URL, token=FAKE_TOOL_TOKEN)
    )
    knowledge_tool = KnowledgeTool(registry)
    validator = AgentActionValidator(
        ControllerCapabilityDiscovery.from_knowledge_tool(knowledge_tool),
        TargetResolver(registry),
    )
    validation = validator.validate(
        AgentAction("grafana.dashboards"),
        HardRequestConstraints(),
        AgentActionToolBudget(),
    )
    calls = 0

    def execute(_arguments: dict[str, object]) -> ToolResult:
        nonlocal calls
        calls += 1
        return ToolResult(success=True)

    monkeypatch.setattr(knowledge_tool, "execute", execute)
    result = AgentActionExecutor(knowledge_tool).execute(
        validation, AgentActionToolBudget()
    )

    assert validation.status is AgentActionValidationStatus.UNAVAILABLE
    assert validation.source_id is None
    assert calls == 0
    assert result.status is AgentActionExecutionStatus.NOT_EXECUTED
    assert result.reason is AgentActionExecutionReason.VALIDATION_NOT_VALID


def test_disappeared_validated_source_does_not_substitute_another_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = fake_environment(grafana=True)
    validator = AgentActionValidator(
        ControllerCapabilityDiscovery.from_knowledge_tool(environment.knowledge_tool),
        environment.target_resolver,
    )
    validation = validator.validate(
        AgentAction("grafana.dashboards"),
        HardRequestConstraints(),
        AgentActionToolBudget(),
    )
    assert validation.status is AgentActionValidationStatus.VALID
    assert validation.source_id == "grafana"
    environment.registry.register_tool(
        "grafana-replacement",
        GrafanaTool(url=FAKE_GRAFANA_URL, token=FAKE_TOOL_TOKEN),
    )
    environment.registry._domain_tools.pop("grafana")
    calls = 0

    def execute(_arguments: dict[str, object]) -> ToolResult:
        nonlocal calls
        calls += 1
        return ToolResult(success=True)

    monkeypatch.setattr(environment.knowledge_tool, "execute", execute)
    result = AgentActionExecutor(environment.knowledge_tool).execute(
        validation, AgentActionToolBudget()
    )

    assert calls == 0
    assert result.status is AgentActionExecutionStatus.NOT_EXECUTED
    assert result.reason is AgentActionExecutionReason.CAPABILITY_BINDING_UNAVAILABLE
    assert result.budget.actions_used == result.budget.tools_used == 0


def test_source_backed_failure_dispatches_once_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = fake_environment(grafana=True)
    validator = AgentActionValidator(
        ControllerCapabilityDiscovery.from_knowledge_tool(environment.knowledge_tool),
        environment.target_resolver,
    )
    validation = validator.validate(
        AgentAction("grafana.dashboards"),
        HardRequestConstraints(),
        AgentActionToolBudget(),
    )
    calls = 0

    def execute(_self: object, _arguments: dict[str, object]) -> ToolResult:
        nonlocal calls
        calls += 1
        return ToolResult(
            success=False,
            error="source unavailable",
            capability_status=CapabilityStatus.COLLECTION_FAILED,
        )

    monkeypatch.setattr("src.tool.grafana_tool.GrafanaTool.execute", execute)
    result = AgentActionExecutor(environment.knowledge_tool).execute(
        validation, AgentActionToolBudget()
    )

    assert validation.source_id == "grafana"
    assert calls == 1
    assert result.status is AgentActionExecutionStatus.FAILURE
    assert result.source_id == "grafana"
    assert result.budget.actions_used == result.budget.tools_used == 1


def test_bridge_has_no_semantic_or_raw_command_dependency() -> None:
    source = inspect.getsource(AgentActionExecutor)

    assert "SemanticPlanBinder" not in source
    assert "Normalizer" not in source
    assert "command" not in AgentActionExecutionResult.__dataclass_fields__
