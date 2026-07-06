from __future__ import annotations

import json

from src.shared.reasoning.action import Action
from src.shared.reasoning.final_response import FinalResponse


def _extract_json_object(response: str) -> dict:
    """
    Find and parse the first valid, top-level JSON object in a string that
    may contain extra text around it (e.g. "Final:", "Action:", "JSON:",
    markdown code fences, or stray whitespace).
    """
    start = response.find("{")

    while start != -1:
        depth = 0
        in_string = False
        escape = False

        for index in range(start, len(response)):
            char = response[index]

            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1

                if depth == 0:
                    candidate = response[start : index + 1]

                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break

        start = response.find("{", start + 1)

    raise ValueError(
        f"No valid JSON object found in model response: {response!r}"
    )


def parse_response(
    response: str,
) -> Action | FinalResponse:
    try:
        data = json.loads(response)
    except json.JSONDecodeError:
        data = _extract_json_object(response)

    if not isinstance(data, dict):
        raise ValueError(
            f"Expected a JSON object in model response, got: {data!r}"
        )

    response_type = data.get("type")

    if response_type == "action":
        if "tool" not in data:
            raise ValueError("Missing tool.")

        if "arguments" not in data:
            raise ValueError("Missing arguments.")

        return Action(
            tool=data["tool"],
            arguments=data["arguments"],
        )

    if response_type == "final":
        if "content" not in data:
            raise ValueError("Missing content.")

        return FinalResponse(
            content=data["content"],
        )

    raise ValueError(f"Unknown response type: {response_type}")
