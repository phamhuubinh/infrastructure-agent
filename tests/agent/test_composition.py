from __future__ import annotations

import inspect

from src.agent.composition import (
    CanonicalAgentComponents,
    build_canonical_agent_components,
    build_canonical_agent_runtime,
)
from src.agent.contracts import AgentDecision, DecisionKind
from src.agent.permissions import PermissionMode
from src.agent.runtime import AgentRuntime, RuntimeTerminal
from src.model.agent_adapter import (
    AgentProviderRequest,
    AgentProviderResponse,
)
from src.tool.knowledge_tool import KnowledgeTool
from src.tool.target_registry import TargetRegistry


class FinalProvider:
    def __init__(self) -> None:
        self.requests: list[AgentProviderRequest] = []

    def generate_agent_decision(
        self,
        request: AgentProviderRequest,
    ) -> AgentProviderResponse:
        self.requests.append(request)
        return AgentProviderResponse(
            payload=AgentDecision(
                kind=DecisionKind.FINAL,
                goal="Answer directly.",
                answer="Canonical runtime works.",
            ).to_wire(),
            provider="fake",
            model="fake-model",
        )


def _empty_tools() -> tuple[TargetRegistry, KnowledgeTool]:
    registry = TargetRegistry()
    return registry, KnowledgeTool(registry)


def test_composition_uses_one_authority_catalog_identity() -> None:
    registry, knowledge = _empty_tools()

    components = build_canonical_agent_components(
        knowledge_tool=knowledge,
        target_registry=registry,
        providers=(FinalProvider(),),
    )

    assert isinstance(components, CanonicalAgentComponents)
    assert components.discovery.capabilities is components.catalog.capabilities
    assert components.authorizer.capabilities is components.catalog.capabilities
    assert components.discovery.targets is components.catalog.targets
    assert components.authorizer.targets is components.catalog.targets
    assert components.discovery.sources is components.catalog.sources
    assert components.authorizer.sources is components.catalog.sources
    assert components.controller.discovery is components.discovery


def test_composition_registers_calculator() -> None:
    registry, knowledge = _empty_tools()

    components = build_canonical_agent_components(
        knowledge_tool=knowledge,
        target_registry=registry,
        providers=(FinalProvider(),),
    )

    capability = components.catalog.capabilities.get(
        "compute.deterministic"
    )

    assert capability is not None
    assert capability.available is True
    assert capability.runtime_binding == "calculator.execute"


def test_composed_runtime_can_answer_directly() -> None:
    registry, knowledge = _empty_tools()
    provider = FinalProvider()

    runtime = build_canonical_agent_runtime(
        knowledge_tool=knowledge,
        target_registry=registry,
        providers=(provider,),
    )

    assert isinstance(runtime, AgentRuntime)

    result = runtime.run(
        "Hello.",
        permission_mode=PermissionMode.READ,
        request_id="composition-test",
    )

    assert result.terminal is RuntimeTerminal.FINAL
    assert result.response_text == "Canonical runtime works."
    assert result.model_calls == 1
    assert result.action_attempts == 0
    assert provider.requests[0].request_id == "composition-test"


def test_no_provider_fails_at_runtime_not_composition() -> None:
    registry, knowledge = _empty_tools()

    runtime = build_canonical_agent_runtime(
        knowledge_tool=knowledge,
        target_registry=registry,
        providers=(),
    )

    result = runtime.run(
        "Hello.",
        permission_mode=PermissionMode.READ,
    )

    assert result.terminal is RuntimeTerminal.FAILED
    assert result.model_calls == 1


def test_composition_has_no_semantic_authority_inputs() -> None:
    parameters = inspect.signature(
        build_canonical_agent_components
    ).parameters

    forbidden = {
        "hard_constraints",
        "semantic_plan",
        "request_semantics",
        "target_resolver",
        "source_constraints",
        "raw_request",
        "intent",
    }

    assert forbidden.isdisjoint(parameters)
