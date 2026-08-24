from __future__ import annotations

import json

from src.agent.contracts import AgentAction, AgentObservation, ObservationStatus
from src.agent.discovery import (
    CapabilityDetail,
    CapabilityDetailStatus,
    DiscoveryResult,
    DiscoveryStatus,
)
from src.model.agent_prompt import (
    build_action_detail_prompt,
    build_discovery_prompt,
    build_first_prompt,
    build_observation_prompt,
    serialized_prompt_sizes,
)


def _bytes(value: object) -> int:
    return len(
        json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
    )


def _detail() -> CapabilityDetail:
    return CapabilityDetail(
        CapabilityDetailStatus.DISCLOSED,
        capability_id="host.cpu",
        detail={
            "capability_id": "host.cpu",
            "purpose": "Inspect CPU",
            "tool_id": "linux",
            "effect": "read",
            "arguments_schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"window": {"type": "integer"}},
                "required": ["window"],
            },
            "target_refs": ["monitor"],
            "source_refs": [],
            "budget_cost": 1,
        },
    )


def test_representative_prompt_and_schema_sizes_shrink_from_v2_fixtures() -> None:
    request = "Check monitor CPU for the last minute."
    summaries = (
        {
            "capability_id": "host.cpu",
            "purpose": "Inspect CPU",
            "effect": "read",
            "tool_id": "linux",
            "target_kind": "machine",
            "result_kind": "observation",
        },
    )
    observation = AgentObservation(
        action_id=1,
        capability_id="host.cpu",
        status=ObservationStatus.SUCCESS,
        target_ref="monitor",
        summary="CPU collected.",
        facts=({"metric": "cpu.percent", "value": 30},),
    )
    prompts = {
        "FIRST": build_first_prompt(
            request,
            capability_groups=("calculator", "host"),
            capability_group_guidance=(
                {
                    "group": "calculator",
                    "purposes": ["Perform exact arithmetic"],
                    "result_kinds": ["deterministic_result"],
                },
                {
                    "group": "host",
                    "purposes": ["Inspect CPU"],
                    "result_kinds": ["observation"],
                },
            ),
        ),
        "DISCOVERY": build_discovery_prompt(
            request,
            DiscoveryResult(
                DiscoveryStatus.DISCOVERED, group="host", summaries=summaries
            ),
            additional_capability_groups=("calculator",),
        ),
        "ACTION_DETAIL": build_action_detail_prompt(
            request,
            proposed_action=AgentAction(
                capability_id="host.cpu", target_ref="monitor", arguments={}
            ),
            detail=_detail(),
        ),
        "OBSERVATION": build_observation_prompt(
            request,
            observations=(observation,),
            capability_groups=("calculator", "host"),
        ),
    }
    sizes = {name: serialized_prompt_sizes(prompt) for name, prompt in prompts.items()}

    # v2 repeated stage prose, nullable root fields, and (for ACTION_DETAIL)
    # both the selected schema and its full detail in user content. These
    # fixtures are intentionally static so size regressions are deterministic.
    v2_user_bytes = {
        "FIRST": _bytes(
            {
                "request": request,
                "capability_groups": ["calculator", "host"],
                "capability_group_guidance": json.loads(prompts["FIRST"].user_prompt)[
                    "groups"
                ],
                "instructions": "Answer with FINAL when no registered capability is needed. If a registered capability may be needed, return DISCOVER with category equal to exactly one value from capability_groups. Never return ACTION at this stage because no capability ID has been disclosed yet.",
            }
        ),
        "DISCOVERY": _bytes(
            {
                "request": request,
                "discovery": {"group": "host", "capabilities": list(summaries)},
                "additional_capability_groups": ["calculator"],
                "instructions": "These exact capabilities are now disclosed. To use one capability, propose ACTION with its exact capability_id. DISCOVER is only for a group in additional_capability_groups.",
            }
        ),
        "ACTION_DETAIL": _bytes(
            {
                "request": request,
                "proposed_action": AgentAction(
                    capability_id="host.cpu", target_ref="monitor", arguments={}
                ).to_wire(),
                "capability": _detail().detail,
                "instructions": "Return ACTION again using this exact capability_id. Choose target_ref/source_ref only from disclosed refs and provide arguments that satisfy the closed schema.",
            }
        ),
        "OBSERVATION": _bytes(
            {
                "request": request,
                "observations": [observation.to_wire()],
                "capability_groups": ["calculator", "host"],
                "instructions": "Use the observations as evidence. Decide whether to answer, discover another capability group, propose another action, clarify, or refuse.",
            }
        ),
    }
    v2_schema_bytes = {
        "FIRST": 4200,
        "DISCOVERY": 5600,
        "ACTION_DETAIL": 2500,
        "OBSERVATION": 6400,
    }

    for stage, metric in sizes.items():
        assert metric["user_bytes"] < v2_user_bytes[stage]
        assert metric["schema_bytes"] < v2_schema_bytes[stage]
