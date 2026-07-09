from __future__ import annotations

from src.model.model_adapter import ModelAdapter
from src.shared.discovery.observation import Observation
from src.shared.reasoning.action import Action
from src.shared.reasoning.final_response import FinalResponse
from src.tool.tool_registry import ToolRegistry


class Agent:
    """
    Coordinates the reasoning loop between the Model and Tools.
    """

    def __init__(
        self,
        model: ModelAdapter,
        tool_registry: ToolRegistry,
        available_resources: dict[str, list[str]] | None = None,
    ) -> None:
        self._model = model
        self._tool_registry = tool_registry
        self._available_resources = available_resources

    def run(
        self,
        user_request: str,
    ) -> str:
        observations: tuple[Observation, ...] = ()

        while True:

            decision = self._model.reason(
                user_request=user_request,
                observations=observations,
                available_resources=self._available_resources,
            )
            if isinstance(decision, FinalResponse):
                return decision.content

            if not isinstance(decision, Action):
                raise TypeError(
                    f"Unsupported reasoning result: {type(decision).__name__}"
                )

            try:
                tool = self._tool_registry.get(
                    decision.tool,
                )

                result = tool.execute(
                    decision.arguments,
                )
            except Exception as exc:
                observations += (
                    Observation(
                        data=None,
                        success=False,
                        error=str(exc),
                        tool=decision.tool,
                        arguments=decision.arguments,
                    ),
                )
                continue

            observations += (
                Observation(
                    data=result.data,
                    success=result.success,
                    error=result.error,
                    tool=decision.tool,
                    arguments=decision.arguments,
                ),
            )
