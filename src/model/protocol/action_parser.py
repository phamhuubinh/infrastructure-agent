from __future__ import annotations

import json

from src.shared.reasoning.action import Action
from src.shared.reasoning.final_response import FinalResponse


def parse_response(
    response: str,
) -> Action | FinalResponse:
    data = json.loads(response)

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
