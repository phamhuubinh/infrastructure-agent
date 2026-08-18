from __future__ import annotations

import pytest

from src.pipeline.input_context_budget import (
    EnforcedInputContext,
    InputContextBudget,
    InputContextBudgetClass,
    InputContextBudgetError,
    InputContextBudgetPolicy,
    InputContextSection,
)
from src.pipeline.response_budget import ResponseBudgetPolicy


def test_budget_classes_have_explicit_char_limits_and_token_estimates() -> None:
    assert (
        InputContextBudgetPolicy.SIMPLE.budget_class is InputContextBudgetClass.SIMPLE
    )
    assert InputContextBudgetPolicy.SIMPLE.max_chars == 6_500
    assert InputContextBudgetPolicy.SIMPLE.max_estimated_tokens == (
        ResponseBudgetPolicy.estimated_tokens_from_chars(6_500)
    )
    assert InputContextBudgetPolicy.NORMAL.max_chars == 4_000
    assert InputContextBudgetPolicy.NORMAL.max_estimated_tokens == (
        ResponseBudgetPolicy.estimated_tokens_from_chars(4_000)
    )
    assert (
        InputContextBudgetPolicy.EVIDENCE_ASSISTED.budget_class
        is InputContextBudgetClass.EVIDENCE_ASSISTED
    )
    assert InputContextBudgetPolicy.EVIDENCE_ASSISTED.max_chars == 16_000
    assert (
        InputContextBudgetPolicy.for_class(InputContextBudgetClass.SIMPLE)
        is InputContextBudgetPolicy.SIMPLE
    )


def test_estimates_reuse_the_existing_token_estimation_policy() -> None:
    text = "Kiểm tra CPU trên monitor với dữ liệu thực tế."
    assert InputContextBudget.estimated_tokens(text) == (
        ResponseBudgetPolicy.estimated_tokens(text)
    )
    assert InputContextBudget.estimated_tokens(text) == (len(text) + 3) // 4


def test_mandatory_sections_are_kept_and_optional_dropped_in_priority_order() -> None:
    budget = InputContextBudget(InputContextBudgetClass.NORMAL, max_chars=100)
    enforced = budget.enforce(
        mandatory=(
            InputContextSection("system", "a" * 40),
            InputContextSection("user_request", "b" * 30),
        ),
        optional=(
            InputContextSection("first_priority", "c" * 20),
            InputContextSection("second_priority", "d" * 40),
            InputContextSection("third_priority", "e" * 10),
        ),
    )

    # 70 mandatory + 20 first = 90; second would be 130 -> dropped with the rest.
    assert enforced.total_chars == 90
    assert enforced.within_budget
    assert enforced.mandatory_names == ("system", "user_request")
    assert enforced.optional_included == ("first_priority",)
    assert enforced.optional_dropped == ("second_priority", "third_priority")
    assert enforced.estimated_input_tokens == (
        ResponseBudgetPolicy.estimated_tokens_from_chars(90)
    )


def test_mandatory_overflow_fails_deterministically() -> None:
    budget = InputContextBudget(InputContextBudgetClass.SIMPLE, max_chars=50)
    with pytest.raises(InputContextBudgetError, match="50-character"):
        budget.enforce(
            mandatory=(InputContextSection("user_request", "x" * 51),),
        )
    # InputContextBudgetError is a ValueError, so generic error handling
    # treats it like any other deterministic construction rejection.
    with pytest.raises(ValueError, match="Mandatory input context"):
        budget.enforce(
            mandatory=(InputContextSection("user_request", "x" * 51),),
            optional=(InputContextSection("context", "y"),),
        )


def test_optional_alone_cannot_trigger_rejection() -> None:
    budget = InputContextBudget(InputContextBudgetClass.NORMAL, max_chars=60)
    enforced = budget.enforce(
        mandatory=(InputContextSection("system", "a" * 10),),
        optional=(
            InputContextSection("context", "b" * 500),
            InputContextSection("more", "c" * 10),
        ),
    )
    assert enforced.total_chars == 10
    assert enforced.optional_included == ()
    assert enforced.optional_dropped == ("context", "more")


def test_enforcement_is_deterministic_across_repeated_construction() -> None:
    budget = InputContextBudget(InputContextBudgetClass.EVIDENCE_ASSISTED, 100)
    sections = {
        "mandatory": (
            InputContextSection("instructions", "I" * 40),
            InputContextSection("evidence", "E" * 30),
        ),
        "optional": (
            InputContextSection("failures", "F" * 20),
            InputContextSection("findings", "G" * 80),
        ),
    }
    first = budget.enforce(
        mandatory=sections["mandatory"], optional=sections["optional"]
    )
    second = budget.enforce(
        mandatory=sections["mandatory"], optional=sections["optional"]
    )

    assert first == second
    assert isinstance(first, EnforcedInputContext)
    assert first.total_chars == 90
    assert first.optional_included == ("failures",)


def test_budget_requires_a_positive_limit() -> None:
    with pytest.raises(ValueError, match="positive"):
        InputContextBudget(InputContextBudgetClass.SIMPLE, max_chars=0)
