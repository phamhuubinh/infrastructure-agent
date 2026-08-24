from __future__ import annotations

import inspect
import json

from src.agent.authority import (
    ExactReferenceRegistry,
    ReferenceEntry,
)
from src.agent.capabilities import (
    CapabilityDefinition,
    CapabilityRegistry,
)
from src.agent.contracts import (
    AgentAction,
    AgentDecision,
    DecisionKind,
)
from src.agent.discovery import (
    CapabilityDiscovery,
    DiscoveryResult,
    DiscoveryStatus,
)
from src.agent.permissions import EffectClass
from src.model.agent_adapter import (
    AgentModelAdapter,
    AgentProviderRequest,
    AgentProviderResponse,
)
from src.model.agent_decision_controller import (
    AgentDecisionController,
)


class FakeProvider:
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
                goal="Answer.",
                answer="Done.",
            ).to_wire(),
            provider="fake",
            model="fake-model",
        )


def _controller() -> tuple[
    AgentDecisionController,
    FakeProvider,
]:
    provider = FakeProvider()

    capability = CapabilityDefinition(
        capability_id="host.cpu",
        purpose="Inspect CPU",
        tool_id="linux",
        effect=EffectClass.READ,
        arguments_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "window": {
                    "type": "integer",
                },
            },
            "required": ["window"],
        },
        runtime_binding="linux.cpu",
        discovery_group="host",
        target_kind="machine",
        allowed_target_refs=frozenset(
            {"monitor"}
        ),
    )

    discovery = CapabilityDiscovery(
        CapabilityRegistry((capability,)),
        ExactReferenceRegistry(
            (
                ReferenceEntry(
                    "monitor",
                    "machine",
                ),
            )
        ),
        ExactReferenceRegistry(()),
    )

    return (
        AgentDecisionController(
            model=AgentModelAdapter([provider]),
            discovery=discovery,
        ),
        provider,
    )


def test_first_decision_uses_registry_groups() -> None:
    controller, provider = _controller()

    result = controller.decide_first(
        "Check CPU.",
        request_id="req-1",
    )

    assert result.decision.kind is DecisionKind.FINAL

    payload = json.loads(
        provider.requests[0].user_prompt
    )

    assert payload["groups"][0]["group"] == "host"
    assert provider.requests[0].request_id == "req-1"


def test_discovery_decision_uses_registry_summaries() -> None:
    controller, provider = _controller()

    controller.decide_after_discovery(
        "Check CPU.",
        result=DiscoveryResult(
            DiscoveryStatus.DISCOVERED,
            group="host",
            summaries=(
                {
                    "capability_id": "host.cpu",
                    "purpose": "Inspect CPU",
                    "effect": "read",
                    "tool_id": "linux",
                    "target_kind": "machine",
                    "result_kind": "observation",
                },
            ),
        ),
        additional_capability_groups=(),
    )

    payload = json.loads(
        provider.requests[0].user_prompt
    )

    assert payload["capabilities"][0][
        "capability_id"
    ] == "host.cpu"


def test_action_detail_uses_same_registry_schema() -> None:
    controller, provider = _controller()

    controller.decide_with_action_detail(
        "Check CPU.",
        proposed_action=AgentAction(
            capability_id="host.cpu",
            target_ref="monitor",
            arguments={},
        ),
    )

    request = provider.requests[0]

    assert request.response_schema["title"] == (
        "OrionAgentDecisionV3"
    )

    action_branch = next(
        branch
        for branch in request.response_schema["oneOf"]
        if branch["properties"]["kind"]["enum"] == ["action"]
    )

    action = action_branch["properties"]["action"]

    assert action["properties"]["capability_id"]["enum"] == [
        "host.cpu"
    ]
    assert action["properties"]["arguments"][
        "required"
    ] == ["window"]


def test_new_model_path_has_no_legacy_semantic_inputs() -> None:
    for method_name in (
        "decide_first",
        "decide_after_discovery",
        "decide_with_action_detail",
        "decide_after_observation",
        "decide_after_feedback",
    ):
        parameters = inspect.signature(
            getattr(
                AgentDecisionController,
                method_name,
            )
        ).parameters

        assert "hard_constraints" not in parameters
        assert "semantic_plan" not in parameters
        assert "target_resolver" not in parameters
        assert "source_constraints" not in parameters
