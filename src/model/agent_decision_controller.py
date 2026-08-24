"""Model-facing progressive disclosure over canonical agent metadata.

This component does not validate or execute actions. It only builds bounded
model inputs from the canonical discovery registry and asks AgentModelAdapter
for one structured decision.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from src.agent.contracts import (
    AgentAction,
    AgentObservation,
)
from src.agent.discovery import (
    CapabilityDetailStatus,
    CapabilityDiscovery,
    DiscoveryResult,
    DiscoveryStatus,
)
from src.model.agent_adapter import (
    AgentDecisionResult,
    AgentModelAdapter,
)
from src.model.agent_prompt import (
    build_action_detail_prompt,
    build_discovery_prompt,
    build_feedback_prompt,
    build_first_prompt,
    build_observation_prompt,
)


class AgentDecisionController:
    """Bounded model I/O using canonical capability discovery only."""

    def __init__(
        self,
        *,
        model: AgentModelAdapter,
        discovery: CapabilityDiscovery,
    ) -> None:
        if not isinstance(model, AgentModelAdapter):
            raise TypeError(
                "model must be AgentModelAdapter."
            )

        if not isinstance(discovery, CapabilityDiscovery):
            raise TypeError(
                "discovery must be CapabilityDiscovery."
            )

        self._model = model
        self._discovery = discovery

    @property
    def discovery(self) -> CapabilityDiscovery:
        return self._discovery

    def decide_first(
        self,
        request: str,
        *,
        request_id: str | None = None,
    ) -> AgentDecisionResult:
        prompt = build_first_prompt(
            request,
            capability_groups=self._discovery.groups(),
            capability_group_guidance=self._discovery.group_guidance(),
        )
        return self._decide(
            prompt,
            request_id=request_id,
        )

    def decide_after_discovery(
        self,
        request: str,
        *,
        result: DiscoveryResult,
        additional_capability_groups: Sequence[str],
        request_id: str | None = None,
    ) -> AgentDecisionResult:
        if result.status is not DiscoveryStatus.DISCOVERED:
            raise ValueError(
                f"Capability group is not discoverable: "
                f"{result.status.value}."
            )

        prompt = build_discovery_prompt(
            request,
            result,
            additional_capability_groups=additional_capability_groups,
        )
        return self._decide(
            prompt,
            request_id=request_id,
        )

    def decide_with_action_detail(
        self,
        request: str,
        *,
        proposed_action: AgentAction,
        request_id: str | None = None,
    ) -> AgentDecisionResult:
        detail = self._discovery.selected_detail(
            proposed_action.capability_id
        )

        if (
            detail.status
            is not CapabilityDetailStatus.DISCLOSED
        ):
            raise ValueError(
                f"Capability detail is not disclosable: "
                f"{detail.status.value}."
            )

        prompt = build_action_detail_prompt(
            request,
            proposed_action=proposed_action,
            detail=detail,
        )

        return self._decide(
            prompt,
            request_id=request_id,
        )

    def decide_after_observation(
        self,
        request: str,
        *,
        observations: Sequence[AgentObservation],
        request_id: str | None = None,
    ) -> AgentDecisionResult:
        prompt = build_observation_prompt(
            request,
            observations=observations,
            capability_groups=self._discovery.groups(),
        )

        return self._decide(
            prompt,
            request_id=request_id,
        )

    def decide_after_feedback(
        self,
        request: str,
        *,
        feedback: Mapping[str, object],
        request_id: str | None = None,
    ) -> AgentDecisionResult:
        prompt = build_feedback_prompt(
            request,
            feedback=feedback,
            capability_groups=self._discovery.groups(),
        )

        return self._decide(
            prompt,
            request_id=request_id,
        )

    def _decide(
        self,
        prompt,
        *,
        request_id: str | None,
    ) -> AgentDecisionResult:
        return self._model.decide(
            system_prompt=prompt.system_prompt,
            user_prompt=prompt.user_prompt,
            selected_capability_schema=(
                prompt.selected_capability_schema
            ),
            response_schema=prompt.response_schema,
            request_id=request_id,
        )


__all__ = ["AgentDecisionController"]
