from __future__ import annotations

from src.pipeline.request_semantics import (
    ExecutionIntent,
    ExternalNeed,
    InformationScope,
    RequestDomain,
    RequestSemantics,
    SourceConstraint,
)


def test_semantics_contract_is_typed_and_explicit() -> None:
    semantics = RequestSemantics(
        domain=(
            RequestDomain
            .EXTERNAL_INFORMATION
        ),
        information_scope=(
            InformationScope
            .CURRENT_EXTERNAL
        ),
        external_need=(
            ExternalNeed.REQUIRED
        ),
        source_constraints=(
            SourceConstraint.INTERNET,
        ),
        execution_intent=(
            ExecutionIntent.EXPLAIN
        ),
    )

    assert semantics.external_need is (
        ExternalNeed.REQUIRED
    )
    assert semantics.source_constraints == (
        SourceConstraint.INTERNET,
    )


def test_unknown_and_unspecified_states_are_not_authority() -> None:
    assert (
        RequestDomain.UNKNOWN
        is not RequestDomain.ACTION
    )
    assert (
        SourceConstraint.UNKNOWN
        is not SourceConstraint.ANY
    )
    assert (
        ExecutionIntent.UNKNOWN
        is not ExecutionIntent
        .MUTATE_ENVIRONMENT
    )


def test_mutation_intent_is_distinct_from_generation() -> None:
    assert (
        ExecutionIntent
        .MUTATE_ENVIRONMENT
        is not ExecutionIntent
        .GENERATE_CONTENT
    )
