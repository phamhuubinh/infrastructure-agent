from __future__ import annotations

from src.pipeline.execution_trace import ResponseStrategy
from src.pipeline.response_budget import ResponseBudgetPolicy


def test_response_budget_policy_covers_each_strategy() -> None:
    expected = {
        ResponseStrategy.GENERAL_EXPLANATION: "assessment",
        ResponseStrategy.TRANSLATION_REWRITE: "assessment",
        ResponseStrategy.SELF_CONTAINED_REASONING: "concise",
        ResponseStrategy.LIVE_ENVIRONMENT: "assessment",
        ResponseStrategy.EXTERNAL_VERIFICATION: "assessment",
        ResponseStrategy.PROVENANCE: "concise",
        ResponseStrategy.MULTI_SOURCE_COMPARISON: "assessment",
        ResponseStrategy.ARTIFACT_GENERATION: "artifact",
        ResponseStrategy.CLARIFICATION_REFUSAL: "concise",
    }
    assert {
        strategy: ResponseBudgetPolicy.for_strategy(strategy).budget_class
        for strategy in ResponseStrategy
    } == expected


def test_artifact_budget_is_larger_than_concise_refusal() -> None:
    artifact = ResponseBudgetPolicy.for_strategy(ResponseStrategy.ARTIFACT_GENERATION)
    refusal = ResponseBudgetPolicy.for_strategy(
        ResponseStrategy.CLARIFICATION_REFUSAL
    )
    assert artifact.max_output_tokens > refusal.max_output_tokens


def test_token_estimate_is_bounded_and_provider_independent() -> None:
    assert ResponseBudgetPolicy.estimated_tokens("") == 0
    assert ResponseBudgetPolicy.estimated_tokens("abcd") == 1
    assert ResponseBudgetPolicy.estimated_tokens("abcde") == 2
