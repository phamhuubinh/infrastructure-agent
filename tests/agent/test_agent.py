from __future__ import annotations

from src.agent.agent import Agent
from src.model.mock_model_adapter import MockModelAdapter
from src.shared.execution.tool_result import ToolResult
from src.shared.reasoning.action import Action
from src.shared.reasoning.final_response import FinalResponse
from src.tool.knowledge_tool import KnowledgeTool
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
        **kwargs,
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
        **kwargs,
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
        **kwargs,
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
        **kwargs,
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


class DockerVersionOnceModel:
    """
    Simulates a model that correctly follows the prompt contract: it
    queries "docker_version" once, sees a successful-but-empty
    Observation, and immediately returns Final instead of repeating the
    exact same call forever (the loop bug being regression-tested here).
    """

    def __init__(self) -> None:
        self._step = 0

    def reason(
        self,
        user_request: str,
        observations,
        **kwargs,
    ):
        self._step += 1

        if self._step == 1:
            return Action(
                tool="knowledge",
                arguments={
                    "source": "linux",
                    "resource": "docker_version",
                },
            )

        observation = observations[-1]

        assert observation.success is True
        assert observation.data == []

        return FinalResponse(
            content="Docker does not appear to be installed on this machine.",
        )


def test_agent_handles_docker_version_empty_result_without_looping(monkeypatch) -> None:
    def fake_execute(self, arguments):
        return ToolResult(success=True, data=[])

    monkeypatch.setattr(
        "src.tool.linux_tool.LinuxTool.execute",
        fake_execute,
    )

    registry = ToolRegistry()

    registry.register(
        tool_id="knowledge",
        tool=KnowledgeTool(),
    )

    agent = Agent(
        model=DockerVersionOnceModel(),
        tool_registry=registry,
    )

    response = agent.run("what version of docker is installed?")

    assert response == "Docker does not appear to be installed on this machine."


class LoopingDockerVersionModel:
    """
    Reproduces the original bug pattern: a model that keeps calling the
    same tool with the exact same arguments whenever it sees an empty
    successful result, instead of treating that result as final. Used to
    confirm the Agent/Tool/Observation layer itself is not the cause of
    the loop: it faithfully reports success=True with an empty value on
    every call and never errors or crashes. The fix for the loop lives in
    the prompt (see tests/model/protocol/test_prompt_builder.py), not in
    this layer.
    """

    def __init__(self, max_calls: int) -> None:
        self.calls = 0
        self._max_calls = max_calls

    def reason(
        self,
        user_request: str,
        observations,
        **kwargs,
    ):
        self.calls += 1

        if self.calls > self._max_calls:
            return FinalResponse(content="gave up")

        return Action(
            tool="knowledge",
            arguments={
                "source": "linux",
                "resource": "docker_version",
            },
        )


def test_knowledge_tool_reports_empty_result_as_success_on_every_repeated_call(
    monkeypatch,
) -> None:
    def fake_execute(self, arguments):
        return ToolResult(success=True, data=[])

    monkeypatch.setattr(
        "src.tool.linux_tool.LinuxTool.execute",
        fake_execute,
    )

    registry = ToolRegistry()

    registry.register(
        tool_id="knowledge",
        tool=KnowledgeTool(),
    )

    model = LoopingDockerVersionModel(max_calls=5)

    agent = Agent(
        model=model,
        tool_registry=registry,
    )

    response = agent.run("what version of docker is installed?")

    assert model.calls == 6
    assert response == "gave up"


def test_observation_carries_the_tool_and_arguments_that_produced_it(
    monkeypatch,
) -> None:
    def fake_execute(self, arguments):
        return ToolResult(success=True, data=[])

    monkeypatch.setattr(
        "src.tool.linux_tool.LinuxTool.execute",
        fake_execute,
    )

    captured = {}

    class CaptureModel:
        def __init__(self) -> None:
            self.step = 0

        def reason(
            self,
            user_request: str,
            observations,
            **kwargs,
        ):
            self.step += 1

            if self.step == 1:
                return Action(
                    tool="knowledge",
                    arguments={
                        "source": "linux",
                        "resource": "docker_version",
                    },
                )

            captured["observation"] = observations[-1]

            return FinalResponse(content="done")

    registry = ToolRegistry()

    registry.register(
        tool_id="knowledge",
        tool=KnowledgeTool(),
    )

    agent = Agent(
        model=CaptureModel(),
        tool_registry=registry,
    )

    agent.run("what version of docker is installed?")

    observation = captured["observation"]

    assert observation.tool == "knowledge"
    assert observation.arguments == {
        "source": "linux",
        "resource": "docker_version",
    }


class DetectsDuplicateActionModel:
    """
    Demonstrates the actual root-cause fix: a model can now recognize that
    an Action was already taken by comparing (tool, arguments) against
    prior Observations -- something impossible before Observation carried
    that context.
    """

    def reason(
        self,
        user_request: str,
        observations,
        **kwargs,
    ):
        already_called = any(
            obs.tool == "knowledge"
            and obs.arguments == {"source": "linux", "resource": "docker_version"}
            for obs in observations
        )

        if already_called:
            return FinalResponse(
                content="already checked, docker is not installed",
            )

        return Action(
            tool="knowledge",
            arguments={
                "source": "linux",
                "resource": "docker_version",
            },
        )


def test_model_can_detect_duplicate_action_using_observation_context(
    monkeypatch,
) -> None:
    def fake_execute(self, arguments):
        return ToolResult(success=True, data=[])

    monkeypatch.setattr(
        "src.tool.linux_tool.LinuxTool.execute",
        fake_execute,
    )

    registry = ToolRegistry()

    registry.register(
        tool_id="knowledge",
        tool=KnowledgeTool(),
    )

    agent = Agent(
        model=DetectsDuplicateActionModel(),
        tool_registry=registry,
    )

    response = agent.run("what version of docker is installed?")

    assert response == "already checked, docker is not installed"
