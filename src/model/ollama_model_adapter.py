from __future__ import annotations

from src.infrastructure.ollama.ollama_client import OllamaClient
from src.model.model_adapter import ModelAdapter
from src.model.protocol.action_parser import parse_response
from src.model.protocol.prompt_builder import build_prompt
from src.shared.discovery.observation import Observation
from src.shared.reasoning.action import Action
from src.shared.reasoning.final_response import FinalResponse


class OllamaModelAdapter(ModelAdapter):
    """
    Model adapter backed by Ollama.
    """

    def __init__(
        self,
        client: OllamaClient,
    ) -> None:
        self._client = client

    def reason(
        self,
        user_request: str,
        observations: tuple[Observation, ...],
        available_resources: dict[str, list[str]] | None = None,
    ) -> Action | FinalResponse:
        prompt = build_prompt(
            user_request=user_request,
            observations=observations,
            available_resources=available_resources,
        )

        response = self._client.generate(
            prompt,
        )
        print("RAW RESPONSE:")
        print(repr(response))

        return parse_response(
            response,
        )
