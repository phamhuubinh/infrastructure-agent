from __future__ import annotations

import json

from src.model.protocol.semantic_planner_prompt import (
    PlannerPromptContext,
    build_semantic_planner_prompt,
)
from src.pipeline.input_context_budget import (
    InputContextBudgetClass,
    InputContextBudgetPolicy,
)
from src.pipeline.request_semantics import SourceConstraint
from src.pipeline.response_budget import ResponseBudgetPolicy


def test_simple_prompt_is_governed_by_the_simple_budget_class() -> None:
    prompt = build_semantic_planner_prompt("hello")

    assert prompt.input_budget_class == InputContextBudgetClass.SIMPLE.value
    assert len(prompt.system_prompt) + len(prompt.user_prompt) <= (
        InputContextBudgetPolicy.SIMPLE.max_chars
    )
    assert prompt.estimated_input_tokens == (
        ResponseBudgetPolicy.estimated_tokens(prompt.system_prompt + prompt.user_prompt)
    )
    # Ordinary simple requests stay far below the ~1k-input-token target.
    assert prompt.estimated_input_tokens < 1_000


def test_original_user_request_is_never_truncated() -> None:
    request = "Kiểm tra CPU và RAM hiện tại trên monitor." + " " * 0
    prompt = build_semantic_planner_prompt(request)
    payload = json.loads(prompt.user_prompt)

    assert payload["request"] == request
    # The request is mandatory: it must appear verbatim, not sliced.
    assert request in prompt.user_prompt


def test_budgeted_prompt_is_stable_across_repeated_construction() -> None:
    context = PlannerPromptContext(
        target="monitor",
        concept="cpu",
        sources=(SourceConstraint.GRAFANA,),
        excluded_sources=(SourceConstraint.INTERNET,),
    )
    first = build_semantic_planner_prompt("Còn RAM thì sao?", context=context)
    second = build_semantic_planner_prompt("Còn RAM thì sao?", context=context)

    assert first == second
    assert first.estimated_input_tokens == second.estimated_input_tokens


def test_unrelated_context_data_cannot_change_the_simple_call() -> None:
    # Tool registries, capability catalogs, and history are never inputs to
    # this builder, so oversized unrelated data cannot change the call.
    unrelated = {
        "tool_registry": {f"tool-{i}": {"schema": "x" * 10_000} for i in range(50)},
        "capability_catalog": ["cap-" + "y" * 10_000 for _ in range(50)],
        "session_history": [{"role": "user", "content": "z" * 50_000}] * 20,
    }
    before = build_semantic_planner_prompt("hello")
    assert unrelated
    after = build_semantic_planner_prompt("hello")

    assert after == before
    combined = after.system_prompt + after.user_prompt
    assert len(combined) <= InputContextBudgetPolicy.SIMPLE.max_chars
    for forbidden in ("tool-", "cap-", "zzzz"):
        assert forbidden not in combined
