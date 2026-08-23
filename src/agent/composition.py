"""Composition root for the canonical Orion agent runtime."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from src.agent.authority import ActionAuthorizer
from src.agent.authority_bridge import (
    AuthorityCatalog,
    build_legacy_authority_catalog,
)
from src.agent.discovery import CapabilityDiscovery
from src.agent.executor_bridge import CanonicalActionExecutor
from src.agent.runtime import AgentRuntime, AgentRuntimeConfig
from src.model.agent_adapter import (
    AgentModelAdapter,
    StructuredAgentProvider,
)
from src.model.agent_decision_controller import (
    AgentDecisionController,
)
from src.tool.knowledge_tool import KnowledgeTool
from src.tool.target_registry import TargetRegistry


@dataclass(frozen=True, slots=True)
class CanonicalAgentComponents:
    """One internally consistent canonical runtime graph."""

    catalog: AuthorityCatalog
    discovery: CapabilityDiscovery
    authorizer: ActionAuthorizer
    model: AgentModelAdapter
    controller: AgentDecisionController
    executor: CanonicalActionExecutor
    runtime: AgentRuntime

    def __post_init__(self) -> None:
        capabilities = self.catalog.capabilities
        targets = self.catalog.targets
        sources = self.catalog.sources

        if self.discovery.capabilities is not capabilities:
            raise ValueError(
                "discovery must share the catalog capability registry."
            )

        if self.discovery.targets is not targets:
            raise ValueError(
                "discovery must share the catalog target registry."
            )

        if self.discovery.sources is not sources:
            raise ValueError(
                "discovery must share the catalog source registry."
            )

        if self.authorizer.capabilities is not capabilities:
            raise ValueError(
                "authorizer must share the catalog capability registry."
            )

        if self.authorizer.targets is not targets:
            raise ValueError(
                "authorizer must share the catalog target registry."
            )

        if self.authorizer.sources is not sources:
            raise ValueError(
                "authorizer must share the catalog source registry."
            )

        if self.controller.discovery is not self.discovery:
            raise ValueError(
                "controller must share the canonical discovery instance."
            )


def build_canonical_agent_components(
    *,
    knowledge_tool: KnowledgeTool,
    target_registry: TargetRegistry,
    providers: Sequence[StructuredAgentProvider],
    model_timeout_seconds: float = 30.0,
    runtime_config: AgentRuntimeConfig | None = None,
    external_verification: object | None = None,
) -> CanonicalAgentComponents:
    """Build one canonical model-authority-execution runtime graph.

    This function performs composition only. It does not parse user prose,
    select capabilities, grant permissions, execute actions, or choose model
    providers dynamically.
    """

    if not isinstance(knowledge_tool, KnowledgeTool):
        raise TypeError(
            "knowledge_tool must be KnowledgeTool."
        )

    if not isinstance(target_registry, TargetRegistry):
        raise TypeError(
            "target_registry must be TargetRegistry."
        )

    if (
        not isinstance(providers, Sequence)
        or isinstance(providers, (str, bytes))
    ):
        raise TypeError(
            "providers must be a sequence."
        )

    catalog = build_legacy_authority_catalog(
        knowledge_tool,
        target_registry,
    )

    discovery = CapabilityDiscovery(
        catalog.capabilities,
        catalog.targets,
        catalog.sources,
    )

    authorizer = ActionAuthorizer(
        catalog.capabilities,
        catalog.targets,
        catalog.sources,
    )

    model = AgentModelAdapter(
        providers,
        timeout_seconds=model_timeout_seconds,
    )

    controller = AgentDecisionController(
        model=model,
        discovery=discovery,
    )

    executor = CanonicalActionExecutor(
        knowledge_tool,
        external_verification=external_verification,
    )

    runtime = AgentRuntime(
        controller=controller,
        discovery=discovery,
        authorizer=authorizer,
        capabilities=catalog.capabilities,
        executor=executor,
        config=runtime_config,
    )

    return CanonicalAgentComponents(
        catalog=catalog,
        discovery=discovery,
        authorizer=authorizer,
        model=model,
        controller=controller,
        executor=executor,
        runtime=runtime,
    )


def build_canonical_agent_runtime(
    *,
    knowledge_tool: KnowledgeTool,
    target_registry: TargetRegistry,
    providers: Sequence[StructuredAgentProvider],
    model_timeout_seconds: float = 30.0,
    runtime_config: AgentRuntimeConfig | None = None,
    external_verification: object | None = None,
) -> AgentRuntime:
    """Convenience view for callers that only need the runtime."""

    return build_canonical_agent_components(
        knowledge_tool=knowledge_tool,
        target_registry=target_registry,
        providers=providers,
        model_timeout_seconds=model_timeout_seconds,
        runtime_config=runtime_config,
        external_verification=external_verification,
    ).runtime


__all__ = [
    "CanonicalAgentComponents",
    "build_canonical_agent_components",
    "build_canonical_agent_runtime",
]
