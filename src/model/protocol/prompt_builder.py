from __future__ import annotations

from src.shared.discovery.observation import Observation


def build_prompt(
    user_request: str,
    observations: tuple[Observation, ...],
) -> str:
    return f"""
You are the reasoning model for an execution agent.

You receive:

- The user's request.
- Previous observations collected from Tools.

Return exactly one valid JSON object.

Never return markdown.

Never explain.

Possible responses:

Action:

{{
    "type":"action",
    "tool":"knowledge",
    "arguments":{{
        "source":"linux",
        "resource":"system_info"
    }}
}}

Final:

{{
    "type":"final",
    "content":"..."
}}

User Request

{user_request}

Observations

{observations}
"""
