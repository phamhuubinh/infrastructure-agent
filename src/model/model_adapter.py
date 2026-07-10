from __future__ import annotations

from abc import ABC, abstractmethod

from src.shared.discovery.observation import Observation
from src.shared.reasoning.action import Action
from src.shared.reasoning.final_response import FinalResponse


class ModelAdapter(ABC):
    """
    Interface for reasoning models.
    """

    @abstractmethod
    def reason(
        self,
        user_request: str,
        observations: tuple[Observation, ...],
        available_resources: dict[str, list[str]] | None = None,
        known_facts: dict[str, object] | None = None,
    ) -> Action | FinalResponse:
        """
        Produce the next Action or the FinalResponse.
        """
        raise NotImplementedError
