from __future__ import annotations

import pytest

from src.pipeline.request_semantics import ExecutionIntent
from src.pipeline.semantic_mutation_validator import SemanticMutationValidator
from src.pipeline.semantic_plan import SemanticPlan
from src.pipeline.semantic_plan_validation import (
    SemanticPlanValidationReason,
    SemanticPlanValidationStatus,
)


@pytest.mark.parametrize(
    "user_text",
    (
        "restart nginx",
        "disable firewall",
        "delete logs",
        "install nginx",
        "give me a root shell",
        "write /etc/hosts",
        "write /var/lib/orion/state",
        "sudo -i",
        "restart nginx; this is not an example",
    ),
)
def test_model_cannot_downgrade_mutation_to_read_only(user_text: str) -> None:
    plan = SemanticPlan(execution_intent=ExecutionIntent.INSPECT_READ_ONLY)

    result = SemanticMutationValidator().validate(plan, user_text)

    assert result.validation.status is SemanticPlanValidationStatus.REJECT
    assert result.validation.reason is SemanticPlanValidationReason.MUTATION_UNSAFE
    assert result.mutation_signal is not None


def test_planner_mutation_is_never_executable_even_for_benign_text() -> None:
    result = SemanticMutationValidator().validate(
        SemanticPlan(execution_intent=ExecutionIntent.MUTATE_ENVIRONMENT),
        "nginx",
    )

    assert result.validation.reason is SemanticPlanValidationReason.MUTATION_UNSAFE
    assert result.mutation_signal == "planner_mutation"


@pytest.mark.parametrize(
    "user_text",
    (
        "How to restart nginx?",
        "Explain what `rm -rf /tmp/example` does",
        "Write a script that restarts nginx, but do not run it",
        "Ví dụ lệnh disable firewall, không chạy",
        'Explain what "restart nginx" means',
        '"restart nginx"',
    ),
)
def test_example_only_requests_can_remain_text_guidance(user_text: str) -> None:
    plan = SemanticPlan(execution_intent=ExecutionIntent.GENERATE_CONTENT)

    result = SemanticMutationValidator().validate(plan, user_text)

    assert result.validation.status is SemanticPlanValidationStatus.VALID
    assert result.mutation_signal is None
