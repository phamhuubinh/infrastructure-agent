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

    assert "Available tools:" in response
    assert "shell" in response


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
                    "source": "localhost",
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
                "source": "localhost",
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
                        "source": "localhost",
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
        "source": "localhost",
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
            and obs.arguments == {"source": "localhost", "resource": "docker_version"}
            for obs in observations
        )

        if already_called:
            return FinalResponse(
                content="already checked, docker is not installed",
            )

        return Action(
            tool="knowledge",
            arguments={
                "source": "localhost",
                "resource": "docker_version",
            },
        )


def test_agent_loop_terminates_after_max_iterations() -> None:
    """
    Regression test: if the model never returns FinalResponse,
    the loop must terminate after max_iterations instead of running forever.
    """
    class InfiniteLoopModel:
        def reason(self, user_request, observations, **kwargs):
            return Action(tool="shell", arguments={"command": "echo loop"})

    registry = ToolRegistry()
    registry.register(tool_id="shell", tool=ShellTool())

    agent = Agent(model=InfiniteLoopModel(), tool_registry=registry, max_iterations=3)
    response = agent.run("test")

    assert "Max iterations" in response


def test_agent_returns_final_response_immediately_without_extra_model_calls(
    monkeypatch,
) -> None:
    """
    Regression test: verify the loop terminates on the first FinalResponse
    without calling the model again.
    """
    call_count = 0

    class SingleFinalModel:
        def reason(self, user_request, observations, **kwargs):
            nonlocal call_count
            call_count += 1
            return FinalResponse(content="done")

    registry = ToolRegistry()
    registry.register(tool_id="knowledge", tool=KnowledgeTool())

    agent = Agent(model=SingleFinalModel(), tool_registry=registry)
    response = agent.run("test")

    assert response == "done"
    assert call_count == 1


def test_unknown_tool_error_lists_available_tools() -> None:
    """
    Regression test: when the model emits Action(tool="zabbix", ...)
    the error must list valid tool IDs so the model can self-correct.
    """
    class FirstCallWrongModel:
        def __init__(self) -> None:
            self._step = 0

        def reason(self, user_request, observations, **kwargs):
            self._step += 1
            if self._step == 1:
                return Action(tool="zabbix", arguments={"resource": "get_hosts"})
            observation = observations[-1]
            assert "Available tools:" in observation.error
            assert "knowledge" in observation.error
            return FinalResponse(content="corrected")

    registry = ToolRegistry()
    registry.register(tool_id="knowledge", tool=KnowledgeTool())
    registry.register(tool_id="shell", tool=ShellTool())

    agent = Agent(model=FirstCallWrongModel(), tool_registry=registry)
    response = agent.run("list hosts")
    assert response == "corrected"


class MultiStepZabbixModel:
    """
    Simulates a model that queries multiple Zabbix capabilities
    before returning a final response.
    """

    def __init__(self) -> None:
        self._step = 0

    def reason(self, user_request, observations, **kwargs):
        self._step += 1
        if self._step == 1:
            return Action(
                tool="knowledge",
                arguments={"source": "zabbix", "resource": "get_hosts"},
            )
        if self._step == 2:
            return Action(
                tool="knowledge",
                arguments={"source": "zabbix", "resource": "get_triggers"},
            )
        observation = observations[-1]
        return FinalResponse(content=f"hosts={observation.data}")


def test_multi_step_agent_loop_terminates_within_few_model_calls(
    monkeypatch,
) -> None:
    """
    Regression test: verify a multi-step reasoning loop (action→result→action→result→final)
    terminates promptly without extra iterations.
    """
    call_count = 0
    captured_arguments: list[dict[str, object]] = []

    def fake_knowledge_execute(self, arguments):
        nonlocal call_count
        call_count += 1
        return ToolResult(
            success=True,
            data={"done": True},
        )

    monkeypatch.setattr(
        "src.tool.knowledge_tool.KnowledgeTool.execute",
        fake_knowledge_execute,
    )

    registry = ToolRegistry()
    registry.register(tool_id="knowledge", tool=KnowledgeTool())

    agent = Agent(model=MultiStepZabbixModel(), tool_registry=registry)
    response = agent.run("check zabbix")

    assert "hosts=" in response
    assert call_count == 2


def test_agent_recovers_from_wrong_tool_then_correct_format(monkeypatch) -> None:
    """
    Reproduces the exact integration bug:
    1. Model emits Action(tool="zabbix", ...) - unknown tool
    2. Agent returns failed Observation with available tools
    3. Model corrects to Action(tool="knowledge", arguments={"source":"zabbix","resource":"get_hosts"})
    4. KnowledgeTool dispatches to ZabbixTool (mocked)
    5. Result returned to model
    6. Model returns FinalResponse
    """
    captured_observations = []

    class TwoStepModel:
        def __init__(self) -> None:
            self._step = 0

        def reason(self, user_request, observations, **kwargs):
            self._step += 1
            captured_observations.extend(observations)

            if self._step == 1:
                return Action(tool="zabbix", arguments={"resource": "get_hosts"})

            if self._step == 2:
                return Action(
                    tool="knowledge",
                    arguments={"source": "zabbix", "resource": "get_hosts"},
                )

            observation = observations[-1]
            return FinalResponse(content=f"result={observation.data}")

    def fake_knowledge_execute(self, arguments):
        if arguments.get("resource") == "get_hosts":
            return ToolResult(
                success=True,
                data={"hosts": [{"hostid": "1", "host": "server01"}]},
            )
        return ToolResult(success=False, error="unknown action")

    monkeypatch.setattr(
        "src.tool.knowledge_tool.KnowledgeTool.execute",
        fake_knowledge_execute,
    )

    registry = ToolRegistry()
    registry.register(tool_id="knowledge", tool=KnowledgeTool())
    registry.register(tool_id="shell", tool=ShellTool())

    agent = Agent(model=TwoStepModel(), tool_registry=registry)
    response = agent.run("list zabbix hosts")
    assert response == "result={'hosts': [{'hostid': '1', 'host': 'server01'}]}"
    assert any(o.success is False and "Available tools:" in o.error for o in captured_observations)
    assert any(o.success is True for o in captured_observations)


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
