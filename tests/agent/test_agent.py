from __future__ import annotations

from src.agent.agent import Agent
from src.model.mock_model_adapter import MockModelAdapter
from src.shared.execution.tool_result import ToolResult
from src.shared.reasoning.action import Action
from src.shared.reasoning.final_response import FinalResponse
from src.tool.shell_tool import ShellTool
from src.tool.tool import Tool
from src.tool.tool_registry import ToolRegistry


def test_agent_runs_reasoning_loop() -> None:
    registry = ToolRegistry()

    registry.register(
        tool_id="shell",
        tool=ShellTool(),
    )

    agent = Agent(
        model=MockModelAdapter(),
        tool_registry=registry,
    )

    response = agent.run("hello")

    assert response.strip() == "hello"


class FailingTool(Tool):
    def execute(
        self,
        arguments: dict[str, object],
    ) -> ToolResult:
        return ToolResult(
            success=False,
            error="command not found",
        )


class ObservationEchoModel:
    def reason(
        self,
        user_request: str,
        observations,
    ):
        if not observations:
            return Action(
                tool="broken",
                arguments={},
            )

        observation = observations[-1]

        return FinalResponse(
            content=f"success={observation.success} error={observation.error}",
        )


def test_agent_propagates_tool_failure_to_model() -> None:
    registry = ToolRegistry()

    registry.register(
        tool_id="broken",
        tool=FailingTool(),
    )

    agent = Agent(
        model=ObservationEchoModel(),
        tool_registry=registry,
    )

    response = agent.run("do something")

    assert response == "success=False error=command not found"


class UnknownToolModel:
    def reason(
        self,
        user_request: str,
        observations,
    ):
        if not observations:
            return Action(
                tool="does_not_exist",
                arguments={},
            )

        observation = observations[-1]

        return FinalResponse(
            content=f"success={observation.success} error={observation.error}",
        )


def test_agent_handles_unknown_tool_without_crashing() -> None:
    registry = ToolRegistry()

    registry.register(
        tool_id="shell",
        tool=ShellTool(),
    )

    agent = Agent(
        model=UnknownToolModel(),
        tool_registry=registry,
    )

    response = agent.run("do something")

    assert response == 'success=False error="Unknown tool: \'does_not_exist\'."'


class MissingArgumentModel:
    def reason(
        self,
        user_request: str,
        observations,
    ):
        if not observations:
            return Action(
                tool="shell",
                arguments={},
            )

        observation = observations[-1]

        return FinalResponse(
            content=f"success={observation.success} error={observation.error}",
        )


def test_agent_handles_invalid_arguments_without_crashing() -> None:
    registry = ToolRegistry()

    registry.register(
        tool_id="shell",
        tool=ShellTool(),
    )

    agent = Agent(
        model=MissingArgumentModel(),
        tool_registry=registry,
    )

    response = agent.run("do something")

    assert response == "success=False error=Missing command."


class RetryAfterDispatchErrorModel:
    def __init__(self) -> None:
        self._step = 0

    def reason(
        self,
        user_request: str,
        observations,
    ):
        self._step += 1

        if self._step == 1:
            return Action(
                tool="does_not_exist",
                arguments={},
            )

        if self._step == 2:
            return Action(
                tool="shell",
                arguments={"command": "echo recovered"},
            )

        return FinalResponse(
            content=str(observations[-1].data),
        )


def test_agent_recovers_after_dispatch_error() -> None:
    registry = ToolRegistry()

    registry.register(
        tool_id="shell",
        tool=ShellTool(),
    )

    agent = Agent(
        model=RetryAfterDispatchErrorModel(),
        tool_registry=registry,
    )

    response = agent.run("do something")

    assert response.strip() == "recovered"
