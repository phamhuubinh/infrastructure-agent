from __future__ import annotations

from src.agent.agent import Agent
from src.model.model_adapter import ModelAdapter
from src.shared.discovery.observation import Observation
from src.shared.execution.tool_result import ToolResult
from src.shared.reasoning.action import Action
from src.shared.reasoning.final_response import FinalResponse
from src.tool.tool import Tool
from src.tool.tool_registry import ToolRegistry


class DummyTool(Tool):
    def execute(
        self,
        arguments: dict[str, object],
    ) -> ToolResult:
        return ToolResult(
            success=True,
            data="hello\n",
        )


class DummyModel(ModelAdapter):
    def __init__(self) -> None:
        self.calls = 0

    def reason(
        self,
        user_request: str,
        observations: tuple[Observation, ...],
    ) -> Action | FinalResponse:
        self.calls += 1

        if not observations:
            return Action(
                tool="dummy",
                arguments={},
            )

        return FinalResponse(
            content=str(observations[-1].data),
        )


def test_agent_runs_reasoning_loop() -> None:
    registry = ToolRegistry()

    registry.register(
        tool_id="dummy",
        tool=DummyTool(),
    )

    model = DummyModel()

    agent = Agent(
        model=model,
        tool_registry=registry,
    )

    response = agent.run("hello")

    assert response == "hello\n"
    assert model.calls == 2
