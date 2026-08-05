from __future__ import annotations

from src.pipeline.execution_budget import (
    BudgetStopReason,
    ExecutionBudget,
    ExecutionBudgetConfig,
)


def test_hard_capability_and_round_limits_cannot_be_reserved_past_limit() -> None:
    budget = ExecutionBudget(
        ExecutionBudgetConfig(
            max_rounds=2,
            max_capabilities=3,
            max_total_duration=10,
            max_estimated_cost=2,
        )
    )

    assert budget.start_round(2, 1.0)
    assert not budget.start_round(2, 0.5)
    assert budget.capabilities == 2
    assert budget.rounds == 1
    assert budget.stop_reason is BudgetStopReason.BUDGET_EXHAUSTED


def test_stop_conditions_are_explicit_and_serializable() -> None:
    budget = ExecutionBudget()
    budget.start_round(1, 0.1)

    assert budget.stop(evidence_sufficient=True) is BudgetStopReason.EVIDENCE_SUFFICIENT
    assert budget.to_dict()["stop_reason"] == "evidence_sufficient"
