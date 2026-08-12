"""Central, soft response-size policy by user-visible strategy."""

from __future__ import annotations

from dataclasses import dataclass

from src.pipeline.execution_trace import ResponseStrategy


@dataclass(frozen=True, slots=True)
class ResponseBudget:
    budget_class: str
    max_output_tokens: int


class ResponseBudgetPolicy:
    """Policy only: correctness text is never truncated to meet a budget."""

    _CONCISE = ResponseBudget("concise", 500)
    _ASSESSMENT = ResponseBudget("assessment", 1_500)
    _ARTIFACT = ResponseBudget("artifact", 3_000)
    _RAW = ResponseBudget("raw_evidence", 2_000)

    @classmethod
    def for_strategy(cls, strategy: ResponseStrategy) -> ResponseBudget:
        if strategy in {
            ResponseStrategy.CLARIFICATION_REFUSAL,
            ResponseStrategy.PROVENANCE,
        }:
            return cls._CONCISE
        if strategy is ResponseStrategy.ARTIFACT_GENERATION:
            return cls._ARTIFACT
        if strategy is ResponseStrategy.SELF_CONTAINED_REASONING:
            return cls._CONCISE
        if strategy in {
            ResponseStrategy.LIVE_ENVIRONMENT,
            ResponseStrategy.EXTERNAL_VERIFICATION,
            ResponseStrategy.MULTI_SOURCE_COMPARISON,
        }:
            return cls._ASSESSMENT
        return cls._ASSESSMENT

    @staticmethod
    def estimated_tokens(text: str) -> int:
        """Conservative, provider-independent estimate for trace reporting."""
        return (len(text) + 3) // 4


__all__ = ["ResponseBudget", "ResponseBudgetPolicy"]
