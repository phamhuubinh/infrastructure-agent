from __future__ import annotations

from src.model.model_adapter import ModelAdapter
from src.shared.discovery.observation import Observation
from src.shared.reasoning.action import Action
from src.shared.reasoning.final_response import FinalResponse


class MockModelAdapter(ModelAdapter):
    """
    Minimal reasoning model used for MVP testing.
    """

    def reason(
        self,
        user_request: str,
        observations: tuple[Observation, ...],
        available_resources: dict[str, list[str]] | None = None,
        known_facts: dict[str, object] | None = None,
    ) -> Action | FinalResponse:
        if not observations:
            return Action(
                tool="shell",
                arguments={
                    "command": f"echo {user_request}",
                },
            )

        return FinalResponse(
            content=str(observations[-1].data),
        )
