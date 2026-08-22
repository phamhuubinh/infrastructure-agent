from __future__ import annotations

from src.agent.controller_contracts import AgentAction, AgentDecision, AgentDecisionKind
from src.agent.controller_loop_coordinator import (
    AgentControllerLoopConfig,
    AgentControllerLoopCoordinator,
)
from src.model.controller_adapter import (
    ControllerAdapter,
    ControllerProviderRequest,
    ControllerProviderResponse,
)
from src.pipeline.agent_action_executor import AgentActionExecutor
from src.pipeline.agent_action_validator import (
    AgentActionToolBudget,
    AgentActionValidationReason,
    AgentActionValidationStatus,
    AgentActionValidator,
)
from src.pipeline.agent_observation_serializer import serialize_execution_observation
from src.pipeline.controller_capability_discovery import ControllerCapabilityDiscovery
from src.pipeline.external_verification import ExternalVerificationExecutor
from src.pipeline.hard_request_constraints import HardRequestConstraints
from tests.fixtures.fake_environment import (
    InternetTool,
    fake_environment,
    raw_search_payload,
)


class _ScriptedController:
    def __init__(self, decisions: list[AgentDecision]) -> None:
        self._decisions = decisions

    def generate_controller(
        self, request: ControllerProviderRequest
    ) -> ControllerProviderResponse:
        return ControllerProviderResponse(
            payload=self._decisions.pop(0).to_wire(),
            provider="fixture",
            model="fixture",
        )


def _components(tool: InternetTool) -> tuple[AgentActionValidator, AgentActionExecutor]:
    environment = fake_environment(internet_tool=tool)
    discovery = ControllerCapabilityDiscovery.from_knowledge_tool(
        environment.knowledge_tool
    )
    return (
        AgentActionValidator(discovery, environment.target_resolver),
        AgentActionExecutor(
            environment.knowledge_tool,
            external_verification_executor=ExternalVerificationExecutor(
                environment.knowledge_tool
            ),
        ),
    )


def test_batched_search_uses_queries_not_individual_controller_actions() -> None:
    tool = InternetTool(
        search_payloads=[raw_search_payload("https://example.test/a")] * 6
    )
    validator, executor = _components(tool)
    budget = AgentActionToolBudget(max_actions=2, max_tools=2)

    first = validator.validate(
        AgentAction("internet.current", {"queries": ["one", "two", "three"]}),
        HardRequestConstraints(),
        budget,
    )
    assert first.status is AgentActionValidationStatus.VALID
    execution = executor.execute(
        first,
        budget,
        raw_request="compare releases",
        hard_constraints=HardRequestConstraints(),
    )
    assert execution.success is True
    assert execution.budget.actions_used == 1
    assert execution.budget.search_queries_used == 3
    assert len(tool.search_calls) == 3
    assert execution.evidence is not None
    assert execution.evidence.evidence_name == "internet_search"
    assert execution.evidence.resource == "web_search"
    observation = serialize_execution_observation(1, execution)
    assert observation.facts[0]["value"]["url"] == "https://example.test/a"
    assert not tool.fetch_calls

    second = validator.validate(
        AgentAction("internet.current", {"queries": ["four", "five", "six"]}),
        HardRequestConstraints(),
        execution.budget,
    )
    assert second.status is AgentActionValidationStatus.VALID
    completed = executor.execute(
        second,
        execution.budget,
        raw_request="compare releases",
        hard_constraints=HardRequestConstraints(),
    )
    assert completed.budget.search_queries_used == 6
    assert completed.budget.actions_used == 2
    assert len(tool.search_calls) == 6


def test_search_batch_over_hard_remaining_is_rejected_before_provider() -> None:
    tool = InternetTool(search_payloads=[raw_search_payload("https://example.test/a")])
    validator, _executor = _components(tool)
    budget = AgentActionToolBudget(search_queries_used=5)

    result = validator.validate(
        AgentAction("internet.current", {"queries": ["six", "seven"]}),
        HardRequestConstraints(),
        budget,
    )

    assert result.status is AgentActionValidationStatus.UNAVAILABLE
    assert result.reason is AgentActionValidationReason.BUDGET_EXHAUSTED
    assert not tool.search_calls


def test_more_than_three_search_queries_is_rejected_before_provider() -> None:
    tool = InternetTool(search_payloads=[raw_search_payload("https://example.test/a")])
    validator, _executor = _components(tool)

    result = validator.validate(
        AgentAction("internet.current", {"queries": ["one", "two", "three", "four"]}),
        HardRequestConstraints(),
        AgentActionToolBudget(),
    )

    assert result.status is AgentActionValidationStatus.REJECT
    assert not tool.search_calls


def test_fetch_budget_blocks_seventh_fetch_before_transport() -> None:
    url = "https://example.test/page"
    tool = InternetTool(
        fetch_payloads={
            url: {
                "url": url,
                "title": "Example page",
                "content_type": "text/html",
                "content_length": 30,
                "content_status": "CONTENT_EXTRACTED",
                "data": "Readable public page evidence.",
            }
        }
    )
    validator, executor = _components(tool)
    budget = AgentActionToolBudget(max_actions=8, max_tools=8)
    action = AgentAction("internet.fetch_url", {"url": url})

    for _ in range(6):
        validation = validator.validate(action, HardRequestConstraints(), budget)
        assert validation.status is AgentActionValidationStatus.VALID
        execution = executor.execute(
            validation,
            budget,
            raw_request="read this page",
            hard_constraints=HardRequestConstraints(),
        )
        budget = execution.budget

    rejected = validator.validate(action, HardRequestConstraints(), budget)
    assert rejected.status is AgentActionValidationStatus.UNAVAILABLE
    assert rejected.reason is AgentActionValidationReason.BUDGET_EXHAUSTED
    assert len(tool.fetch_calls) == 6


def test_new_budget_is_request_scoped_and_starts_fresh() -> None:
    previous_request = AgentActionToolBudget(search_queries_used=6, fetches_used=6)
    next_request = AgentActionToolBudget()

    assert not previous_request.permits_search_queries(1)
    assert not previous_request.permits_fetch()
    assert next_request.permits_search_queries(3)
    assert next_request.permits_fetch()


def test_controller_trace_reports_aggregate_internet_usage() -> None:
    tool = InternetTool(search_payloads=[raw_search_payload("https://example.test/a")])
    environment = fake_environment(internet_tool=tool)
    discovery = ControllerCapabilityDiscovery.from_knowledge_tool(
        environment.knowledge_tool
    )
    action = AgentAction("internet.current", {"query": "release notes"})
    controller = _ScriptedController(
        [
            AgentDecision(
                kind=AgentDecisionKind.DISCOVER,
                goal="Find web search.",
                category="internet",
                clarification_question=None,
            ),
            AgentDecision(
                kind=AgentDecisionKind.ACTION,
                goal="Search the web.",
                action=action,
                clarification_question=None,
            ),
            AgentDecision(
                kind=AgentDecisionKind.ACTION,
                goal="Search the web.",
                action=action,
                clarification_question=None,
            ),
            AgentDecision(
                kind=AgentDecisionKind.FINAL,
                goal="Respond safely.",
                final_answer="Search discovery is available.",
                clarification_question=None,
            ),
        ]
    )
    coordinator = AgentControllerLoopCoordinator(
        controller=ControllerAdapter([controller]),
        discovery=discovery,
        validator=AgentActionValidator(discovery, environment.target_resolver),
        executor=AgentActionExecutor(environment.knowledge_tool),
        config=AgentControllerLoopConfig(max_actions=2, max_tools=2),
    )

    result = coordinator.run(
        "Find current release notes", hard_constraints=HardRequestConstraints()
    )

    internet = result.to_trace_dict()["controller_metrics"]["internet"]
    assert internet["search_actions"] == 1
    assert internet["search_queries"] == 1
    assert internet["fetch_attempts"] == 0
    assert internet["fetched_bytes"] == 0
