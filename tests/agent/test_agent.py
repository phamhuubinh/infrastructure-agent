from __future__ import annotations

from src.agent.agent import Agent
from src.model.mock_model_adapter import MockModelAdapter
from src.tool.shell_tool import ShellTool
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
