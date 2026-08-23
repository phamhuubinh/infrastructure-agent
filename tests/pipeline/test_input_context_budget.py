from __future__ import annotations

import pytest

from src.pipeline.input_context_budget import (
    InputContextBudget,
    InputContextBudgetClass,
    InputContextBudgetError,
    InputContextSection,
)


def test_budget_keeps_optional_sections_that_fit() -> None:
    budget = InputContextBudget(
        InputContextBudgetClass.NORMAL,
        max_chars=10,
    )

    result = budget.enforce(
        mandatory=(
            InputContextSection(
                "request",
                "12345",
            ),
        ),
        optional=(
            InputContextSection(
                "context",
                "123",
            ),
        ),
    )

    assert result.within_budget
    assert result.optional_included == (
        "context",
    )


def test_budget_drops_optional_tail_whole() -> None:
    budget = InputContextBudget(
        InputContextBudgetClass.NORMAL,
        max_chars=7,
    )

    result = budget.enforce(
        mandatory=(
            InputContextSection(
                "request",
                "12345",
            ),
        ),
        optional=(
            InputContextSection("a", "123"),
            InputContextSection("b", "1"),
        ),
    )

    assert result.optional_included == ()
    assert result.optional_dropped == (
        "a",
        "b",
    )


def test_mandatory_overflow_fails_before_provider_call() -> None:
    budget = InputContextBudget(
        InputContextBudgetClass.NORMAL,
        max_chars=3,
    )

    with pytest.raises(
        InputContextBudgetError,
    ):
        budget.enforce(
            mandatory=(
                InputContextSection(
                    "request",
                    "1234",
                ),
            )
        )
