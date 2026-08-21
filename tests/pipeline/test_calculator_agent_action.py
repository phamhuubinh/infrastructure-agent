from __future__ import annotations

from decimal import Decimal

import pytest

from src.agent.controller_contracts import AgentAction
from src.agent.final_response_guard import (
    FinalResponseConstraints,
    FinalResponseGuard,
    FinalResponseViolation,
)
from src.pipeline.agent_action_executor import (
    AgentActionExecutionStatus,
    AgentActionExecutor,
)
from src.pipeline.agent_action_validator import (
    AgentActionToolBudget,
    AgentActionValidationReason,
    AgentActionValidationStatus,
    AgentActionValidator,
)
from src.pipeline.calculator_action_contract import calculator_arguments_schema
from src.pipeline.controller_capability_discovery import ControllerCapabilityDiscovery
from src.pipeline.hard_request_constraints import (
    HardRequestConstraints,
    HardTargetReference,
)
from tests.fixtures.fake_environment import fake_environment


def _arguments(operation: str, **values: object) -> dict[str, object]:
    arguments = {name: None for name in calculator_arguments_schema()["properties"]}
    arguments["operation"] = operation
    arguments.update(values)
    return arguments


def _components() -> tuple[object, AgentActionValidator, AgentActionExecutor]:
    environment = fake_environment()
    validator = AgentActionValidator(
        ControllerCapabilityDiscovery.from_knowledge_tool(environment.knowledge_tool),
        environment.target_resolver,
    )
    return environment, validator, AgentActionExecutor(environment.knowledge_tool)


def _validated(
    validator: AgentActionValidator,
    arguments: dict[str, object],
    *,
    budget: AgentActionToolBudget | None = None,
):
    return validator.validate(
        AgentAction("compute.deterministic", arguments),
        HardRequestConstraints(),
        budget or AgentActionToolBudget(),
    )


def test_calculator_detail_reuses_one_closed_canonical_transport_schema() -> None:
    environment, _, _ = _components()
    selected = ControllerCapabilityDiscovery.from_knowledge_tool(
        environment.knowledge_tool
    ).selected_detail("compute.deterministic", HardRequestConstraints())

    assert selected.selected_capability_schema is not None
    schema = selected.selected_capability_schema["arguments_schema"]
    assert schema == calculator_arguments_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["properties"]["operation"]["type"] == "string"


def test_subtract_action_uses_only_typed_arguments_and_no_knowledge_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment, validator, executor = _components()
    calls = 0

    def execute(_arguments: dict[str, object]) -> None:
        nonlocal calls
        calls += 1
        raise AssertionError("calculator must not dispatch KnowledgeTool")

    monkeypatch.setattr(environment.knowledge_tool, "execute", execute)
    validation = _validated(validator, _arguments("subtract", left=64, right=18))
    result = executor.execute(validation, AgentActionToolBudget())

    assert validation.status is AgentActionValidationStatus.VALID
    assert validation.target_id is validation.source_id is None
    assert result.status is AgentActionExecutionStatus.SUCCESS
    assert result.calculator_result is not None
    assert result.calculator_result.value == Decimal("46")
    assert result.tool_result is result.evidence is None
    assert calls == 0
    assert result.budget.actions_used == result.budget.tools_used == 1


def test_average_uses_exact_action_values_without_legacy_text_parsers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.pipeline.basic_calculator as calculator

    _, validator, executor = _components()

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("legacy arithmetic parser must not run")

    monkeypatch.setattr(calculator, "calculate_supplied_text", forbidden)
    monkeypatch.setattr(calculator, "looks_like_arithmetic", forbidden)
    monkeypatch.setattr(calculator, "calculate", forbidden)
    validation = _validated(validator, _arguments("average", values=[20, 40, 60]))
    result = executor.execute(validation, AgentActionToolBudget())

    assert validation.status is AgentActionValidationStatus.VALID
    assert validation.normalized_arguments["values"] == (20, 40, 60)
    assert result.calculator_result is not None
    assert result.calculator_result.value == Decimal("40")


def test_availability_composition_uses_existing_typed_operations_only() -> None:
    _, validator, executor = _components()
    unavailable_percent = executor.execute(
        _validated(validator, _arguments("subtract", left=100, right=99.9)),
        AgentActionToolBudget(),
    )
    assert unavailable_percent.calculator_result is not None
    assert unavailable_percent.calculator_result.value == Decimal("0.1")

    allowed_downtime = executor.execute(
        _validated(
            validator,
            _arguments("percent_of", base_value=30, percent=0.1, unit="days"),
        ),
        AgentActionToolBudget(),
    )
    assert allowed_downtime.calculator_result is not None
    assert allowed_downtime.calculator_result.value == Decimal("0.03")
    assert allowed_downtime.calculator_result.unit == "days"


def test_invalid_and_unsupported_calculator_requests_remain_typed() -> None:
    _, validator, executor = _components()
    invalid = executor.execute(
        _validated(validator, _arguments("divide", left=4, right=0)),
        AgentActionToolBudget(),
    )
    unsupported = _validated(validator, _arguments("not_an_operation"))

    assert invalid.status is AgentActionExecutionStatus.FAILURE
    assert invalid.calculator_result is not None
    assert invalid.calculator_result.value is None
    assert invalid.calculator_result.reason == "division_by_zero"
    assert unsupported.status is AgentActionValidationStatus.REJECT
    assert unsupported.reason is AgentActionValidationReason.ARGUMENT_INVALID
    assert (
        executor.execute(unsupported, AgentActionToolBudget()).budget.actions_used == 0
    )


@pytest.mark.parametrize(
    "arguments",
    (
        _arguments("average", values=[20, "not-a-number"]),
        _arguments("worker_task_rate", duration_unit="days"),
        _arguments("rate_convert", rate_unit="daily"),
        {**_arguments("add", left=1, right=2), "operation": None},
    ),
)
def test_calculator_transport_rejects_invalid_units_numbers_and_nulls(
    arguments: dict[str, object],
) -> None:
    _, validator, _ = _components()

    validation = _validated(validator, arguments)

    assert validation.status in {
        AgentActionValidationStatus.CLARIFY,
        AgentActionValidationStatus.REJECT,
    }
    assert validation.reason in {
        AgentActionValidationReason.ARGUMENT_REQUIRED,
        AgentActionValidationReason.ARGUMENT_INVALID,
    }


def test_calculator_target_mismatch_and_budget_are_non_executing() -> None:
    _, validator, executor = _components()
    arguments = _arguments("add", left=1, right=2)
    mismatched = validator.validate(
        AgentAction("compute.deterministic", arguments),
        HardRequestConstraints(
            explicit_target=HardTargetReference(
                "localhost", registered_target="localhost"
            )
        ),
        AgentActionToolBudget(),
    )
    exhausted = _validated(
        validator,
        arguments,
        budget=AgentActionToolBudget(max_actions=1, actions_used=1),
    )

    assert mismatched.reason is AgentActionValidationReason.TARGET_MISMATCH
    assert exhausted.reason is AgentActionValidationReason.BUDGET_EXHAUSTED
    assert (
        executor.execute(mismatched, AgentActionToolBudget()).budget.actions_used == 0
    )
    assert executor.execute(exhausted, AgentActionToolBudget()).budget.actions_used == 0


def test_final_guard_rejects_a_conflicting_calculator_action_result() -> None:
    _, validator, executor = _components()
    execution = executor.execute(
        _validated(validator, _arguments("subtract", left=64, right=18)),
        AgentActionToolBudget(),
    )
    assert execution.calculator_result is not None

    guarded = FinalResponseGuard().validate(
        "Result: 45.",
        FinalResponseConstraints(calculator_result=execution.calculator_result),
    )

    assert FinalResponseViolation.CALCULATOR_MISMATCH in guarded.violations
    assert guarded.text == "Result: 46."
