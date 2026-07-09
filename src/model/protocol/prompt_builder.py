from __future__ import annotations

import json

from src.shared.discovery.observation import Observation

RULES = [
    'Use "knowledge" instead of general knowledge for questions about this machine.',
    "Only use resource names listed in available_resources.",
    "Each entry in actions_taken is an Action already executed this "
    "session and its result -- do not repeat one.",
    "A failed entry's error lists valid resources; retry with one of those.",
    'A successful entry with empty data is itself a final answer (e.g. "not installed"), not a reason to retry.',
    "You can only perform actions whose names appear in available_resources. "
    "If the user requests an action that is not listed (e.g. format, delete, reboot), "
    'you cannot perform it. Return type "final" stating the action is not supported.',
    "Do NOT claim an action was performed unless you called it and received a successful ToolResult.",
    "When the user asks multiple questions, call capabilities for each question "
    "one at a time. Only return final after all questions have been answered.",
]

HEALTH_ASSESSMENT_FORMAT = """
When asked for a health assessment or system evaluation:

1. Collect evidence by calling capabilities for each relevant subsystem:
   - CPU: get_cpu, get_cpu_usage
   - Memory: get_memory, get_swap
   - Disk: get_disk
   - Filesystem: get_filesystem
   - Network: get_network
   - Services: get_services
   - System info: get_system, get_uptime, get_time
   - Docker: get_docker
   - Zabbix (if relevant): get_hosts, get_problems, get_triggers

2. Before returning final, ensure you have performed the following reasoning steps:
   a. Review the user's request and determine what evidence is required.
   b. Collect sufficient evidence using capabilities.
   c. Assess each subsystem based ONLY on collected evidence. Never guess.
   d. Determine the overall risk level.
   e. Identify which important subsystems have NOT been inspected.
   f. Produce a concise summary based on evidence.

3. Structure the final response with exactly these sections:

   Evidence
   Raw information returned by capabilities. No interpretation.

   Assessment
   Per-subsystem evaluation. One of: OK / INFO / WARNING / HIGH / CRITICAL.
   Every assessment must reference specific collected evidence.

   Risk
   Overall system risk: OK / INFO / WARNING / HIGH / CRITICAL.
   Must be justified by collected evidence.

   Missing Evidence
   List any important subsystem that was NOT inspected. Never assume an uninspected
   subsystem is healthy. If all relevant subsystems were inspected, state "None".

   Summary
   Concise technical conclusion based only on collected evidence. No redesigns,
   no migrations, no invented observations.

4. Do NOT return final until evidence has been collected for all categories
   listed in step 1, unless the user's request is narrowly scoped.
"""

RESPONSE_EXAMPLES = [
    {
        "type": "action",
        "tool": "knowledge",
        "arguments": {
            "source": "localhost",
            "resource": "get_system",
        },
    },
    {
        "type": "action",
        "tool": "knowledge",
        "arguments": {
            "source": "monitor",
            "resource": "get_system",
        },
    },
    {
        "type": "action",
        "tool": "knowledge",
        "arguments": {
            "source": "zabbix",
            "resource": "get_hosts",
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
        "health_assessment_format": HEALTH_ASSESSMENT_FORMAT,
        "available_resources": available_resources,
        "user_request": user_request,
        "actions_taken": [
            _observation_to_dict(observation) for observation in observations
        ],
    }

    return json.dumps(payload)
