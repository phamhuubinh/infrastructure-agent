from __future__ import annotations

from src.shared.execution.execution_step_result import (
    ExecutionStepResult,
)


def build_prompt(
    user_request: str,
    results: tuple[ExecutionStepResult, ...],
) -> str:
    return f"""
You are the reasoning model for an execution agent.

You must return exactly one valid JSON object.

Never return markdown.

Never explain.

Possible response types:

1.

{{
    "type":"action",
    "tool":"shell",
    "arguments":{{
        "command":"echo hello"
    }}
}}

2.

{{
    "type":"final",
    "content":"..."
}}

User Request

{user_request}

Execution Results

{results}
"""
