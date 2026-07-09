from __future__ import annotations

import json

from src.shared.discovery.observation import Observation

RULES = [
    'Use "knowledge" instead of general knowledge for questions about this machine.',
    "Only use resource names listed in available_resources.",
    "Each entry in actions_taken is an Action already executed this "
    "session and its result -- do not repeat one.",
    "A failed entry's error lists valid resources; retry with one of those.",
    "A successful entry with empty data is itself a final answer (e.g. "
    '"not installed"), not a reason to retry.',
]

RESPONSE_EXAMPLES = [
    {
        "type": "action",
        "tool": "knowledge",
        "arguments": {
            "source": "linux",
            "resource": "system_info",
        },
    },
    {
        "type": "final",
        "content": "...",
    },
]


def _observation_to_dict(
    observation: Observation,
) -> dict[str, object]:
    entry: dict[str, object] = {
        "tool": observation.tool,
        "arguments": observation.arguments,
        "success": observation.success,
    }

    if observation.success:
        entry["data"] = observation.data
    else:
        entry["error"] = observation.error

    return entry


def build_prompt(
    user_request: str,
    observations: tuple[Observation, ...],
    available_resources: dict[str, list[str]] | None = None,
) -> str:
    if available_resources is None:
        from src.tool.knowledge_tool import KnowledgeTool

        available_resources = KnowledgeTool().get_available_resources()

    payload = {
        "role": "reasoning model for an execution agent",
        "output_format": (
            "respond with exactly one of the objects in response_examples "
            "below, unwrapped -- no markdown, no explanation, no extra key "
            "wrapping it"
        ),
        "response_examples": RESPONSE_EXAMPLES,
        "rules": RULES,
        "available_resources": available_resources,
        "user_request": user_request,
        "actions_taken": [
            _observation_to_dict(observation) for observation in observations
        ],
    }

    return json.dumps(payload)
