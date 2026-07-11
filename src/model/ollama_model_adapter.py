from __future__ import annotations

import time as _time

from src.agent.agent import _VERBOSE
from src.infrastructure.ollama.ollama_client import OllamaClient
from src.model.model_adapter import ModelAdapter
from src.model.protocol.action_parser import parse_response
from src.model.protocol.prompt_builder import build_prompt
from src.shared.discovery.observation import Observation
from src.shared.reasoning.action import Action
from src.shared.reasoning.final_response import FinalResponse


def _log(msg: str = "") -> None:
    if _VERBOSE:
        print(msg)


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
        known_facts: dict[str, object] | None = None,
        capability_metadata: dict[str, list[dict[str, object]]] | None = None,
    ) -> Action | FinalResponse:
        t0 = _time.perf_counter()

        prompt = build_prompt(
            user_request=user_request,
            observations=observations,
            available_resources=available_resources,
            known_facts=known_facts,
            capability_metadata=capability_metadata,
        )

        _log(f"[{_time.perf_counter() - t0:.3f}s] build_prompt")

        try:
            t_http = _time.perf_counter()
            response = self._client.generate(prompt)
            _log(f"[{_time.perf_counter() - t_http:.3f}s] generate (HTTP)")
        except Exception as exc:
            _log(f"generate FAILED: {exc}")
            raise

        _log(f"RAW RESPONSE: {response[:200]}...")
        _log(f"[{_time.perf_counter() - t0:.3f}s] response received")

        try:
            result = parse_response(response)
        except ValueError as exc:
            _log(f"parse FAILED: {exc}")
            return FinalResponse(content=f"I received an invalid response from the model: {exc}")

        _log(f"[{_time.perf_counter() - t0:.3f}s] total model time")
        if isinstance(result, Action):
            _log(f"Action tool={result.tool} args={result.arguments}")
        else:
            _log(f"FinalResponse content={str(result.content)[:80]}...")

        return result
