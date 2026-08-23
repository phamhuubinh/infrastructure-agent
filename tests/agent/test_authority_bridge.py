from __future__ import annotations

import sys
from types import ModuleType

from src.agent.authority import (
    ActionAuthorizer,
    AuthorizationReason,
    AuthorityBudget,
)
from src.agent.authority_bridge import (
    build_legacy_authority_catalog,
)
from src.agent.contracts import AgentAction
from src.agent.permissions import EffectClass, PermissionMode
from src.pipeline.calculator_action_contract import (
    CALCULATOR_CAPABILITY_ID,
)
from src.pipeline.internet_action_contract import (
    INTERNET_CURRENT_CAPABILITY_ID,
    INTERNET_FETCH_URL_CAPABILITY_ID,
)
from src.shared.capability import Capability, ParameterSpec
from src.tool.knowledge_tool import KnowledgeTool
from src.tool.target_registry import TargetRegistry
from src.tool.tool import Tool


def _handler(**kwargs: object) -> dict[str, object]:
    return dict(kwargs)


def _fake_tool(
    monkeypatch,
    *,
    class_name: str,
    capabilities: dict[str, Capability],
) -> Tool:
    module_name = (
        f"tests.fake_authority_bridge_"
        f"{class_name.casefold()}_{id(capabilities)}"
    )
    module = ModuleType(module_name)
    module._CAPABILITIES = capabilities  # type: ignore[attr-defined]

    class FakeTool(Tool):
        def execute(
            self,
            arguments: dict[str, object],
        ):
            raise AssertionError(
                "authority bridge must never execute tools"
            )

    FakeTool.__name__ = class_name
    FakeTool.__qualname__ = class_name
    FakeTool.__module__ = module_name

    setattr(module, class_name, FakeTool)
    monkeypatch.setitem(sys.modules, module_name, module)

    return FakeTool()


def test_bridge_projects_linux_targets_as_exact_machine_refs() -> None:
    registry = TargetRegistry()
    registry.add("monitor")
    registry.add("server01")
    knowledge = KnowledgeTool(registry)

    catalog = build_legacy_authority_catalog(
        knowledge,
        registry,
    )

    assert catalog.targets.get("monitor") is not None
    assert catalog.targets.get("server01") is not None
    assert catalog.targets.get("Monitor") is None
    assert catalog.sources.get("monitor") is None

    metadata = knowledge.get_capability_metadata()["monitor"]
    read_entry = next(
        entry
        for entry in metadata
        if entry.get("mutation_risk") == "none"
        and isinstance(entry.get("name"), str)
    )
    capability_id = f"host.{read_entry['name']}"
    capability = catalog.capabilities.get(capability_id)

    assert capability is not None
    assert capability.effect is EffectClass.READ
    assert capability.target_kind == "machine"
    assert capability.source_kind is None
    assert capability.allowed_target_refs == frozenset(
        {"monitor", "server01"}
    )


def test_bridge_projects_domain_source_scope_exactly(
    monkeypatch,
) -> None:
    grafana = _fake_tool(
        monkeypatch,
        class_name="GrafanaTool",
        capabilities={
            "metrics": Capability(
                name="metrics",
                handler=_handler,
                description="Read Grafana metrics",
                parameters=("window",),
                parameter_specs=(
                    ParameterSpec(
                        name="window",
                        required=True,
                        value_type="int",
                        minimum=1,
                        maximum=300,
                    ),
                ),
                mutation_risk="none",
            )
        },
    )

    registry = TargetRegistry()
    registry.register_domain_tool("grafana-prod", grafana)
    knowledge = KnowledgeTool(registry)

    catalog = build_legacy_authority_catalog(
        knowledge,
        registry,
    )

    capability = catalog.capabilities.get(
        "grafana.metrics"
    )

    assert capability is not None
    assert capability.source_kind == "grafana"
    assert capability.target_kind is None
    assert capability.allowed_source_refs == frozenset(
        {"grafana-prod"}
    )

    result = ActionAuthorizer(
        catalog.capabilities,
        catalog.targets,
        catalog.sources,
    ).authorize(
        AgentAction(
            capability_id="grafana.metrics",
            source_ref="grafana-prod",
            arguments={"window": 60},
        ),
        permission_mode=PermissionMode.READ,
        budget=AuthorityBudget(),
    )

    assert result.valid


def test_bridge_unions_only_sources_that_expose_capability(
    monkeypatch,
) -> None:
    with_metrics = _fake_tool(
        monkeypatch,
        class_name="GrafanaTool",
        capabilities={
            "metrics": Capability(
                name="metrics",
                handler=_handler,
                description="Read Grafana metrics",
                mutation_risk="none",
            )
        },
    )
    without_metrics = _fake_tool(
        monkeypatch,
        class_name="GrafanaTool",
        capabilities={
            "alerts": Capability(
                name="alerts",
                handler=_handler,
                description="Read Grafana alerts",
                mutation_risk="none",
            )
        },
    )

    registry = TargetRegistry()
    registry.register_domain_tool(
        "grafana-prod",
        with_metrics,
    )
    registry.register_domain_tool(
        "grafana-empty",
        without_metrics,
    )
    knowledge = KnowledgeTool(registry)

    catalog = build_legacy_authority_catalog(
        knowledge,
        registry,
    )
    capability = catalog.capabilities.get(
        "grafana.metrics"
    )

    assert capability is not None
    assert capability.allowed_source_refs == frozenset(
        {"grafana-prod"}
    )

    result = ActionAuthorizer(
        catalog.capabilities,
        catalog.targets,
        catalog.sources,
    ).authorize(
        AgentAction(
            capability_id="grafana.metrics",
            source_ref="grafana-empty",
            arguments={},
        ),
        permission_mode=PermissionMode.READ,
        budget=AuthorityBudget(),
    )

    assert (
        result.reason
        is AuthorizationReason.SOURCE_NOT_SUPPORTED
    )


def test_legacy_write_is_classified_but_disabled_until_review(
    monkeypatch,
) -> None:
    grafana = _fake_tool(
        monkeypatch,
        class_name="GrafanaTool",
        capabilities={
            "set_alert": Capability(
                name="set_alert",
                handler=_handler,
                description="Change alert configuration",
                mutation_risk="high",
            )
        },
    )

    registry = TargetRegistry()
    registry.register_domain_tool(
        "grafana-prod",
        grafana,
    )
    knowledge = KnowledgeTool(registry)

    catalog = build_legacy_authority_catalog(
        knowledge,
        registry,
    )
    capability = catalog.capabilities.get(
        "grafana.set_alert"
    )

    assert capability is not None
    assert capability.effect is EffectClass.WRITE
    assert capability.available is False
    assert capability.safety_reviewed is False


def test_bridge_exposes_reviewed_high_level_internet_not_raw_primitives(
    monkeypatch,
) -> None:
    internet = _fake_tool(
        monkeypatch,
        class_name="InternetTool",
        capabilities={
            "web_search": Capability(
                name="web_search",
                handler=_handler,
                mutation_risk="none",
            ),
            "web_fetch": Capability(
                name="web_fetch",
                handler=_handler,
                mutation_risk="none",
            ),
        },
    )

    registry = TargetRegistry()
    registry.register_domain_tool(
        "internet-main",
        internet,
    )
    knowledge = KnowledgeTool(registry)

    catalog = build_legacy_authority_catalog(
        knowledge,
        registry,
    )

    assert (
        catalog.capabilities.get("internet.web_search")
        is None
    )
    assert (
        catalog.capabilities.get("internet.web_fetch")
        is None
    )

    current = catalog.capabilities.get(
        INTERNET_CURRENT_CAPABILITY_ID
    )
    fetch = catalog.capabilities.get(
        INTERNET_FETCH_URL_CAPABILITY_ID
    )

    assert current is not None
    assert fetch is not None
    assert current.allowed_source_refs == frozenset(
        {"internet-main"}
    )
    assert fetch.allowed_source_refs == frozenset(
        {"internet-main"}
    )


def test_bridge_always_registers_deterministic_calculator() -> None:
    registry = TargetRegistry()
    knowledge = KnowledgeTool(registry)

    catalog = build_legacy_authority_catalog(
        knowledge,
        registry,
    )

    calculator = catalog.capabilities.get(
        CALCULATOR_CAPABILITY_ID
    )

    assert calculator is not None
    assert calculator.effect is EffectClass.READ
    assert calculator.target_kind is None
    assert calculator.source_kind is None
    assert calculator.safety_reviewed is True
