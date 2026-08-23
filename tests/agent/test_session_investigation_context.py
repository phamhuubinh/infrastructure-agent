from __future__ import annotations

from src.agent.session_investigation_context import (
    EvidenceReceipt,
    SessionContextResolver,
    SessionInvestigationContext,
)
from src.pipeline.request_semantics import (
    SourceConstraint,
)


def test_context_round_trip_preserves_bounded_state() -> None:
    context = SessionInvestigationContext(
        active_target="monitor",
        active_concept="cpu",
        active_service="nginx",
        incident_ids=("INC-407",),
        active_sources=(
            SourceConstraint.GRAFANA,
        ),
    )

    restored = (
        SessionInvestigationContext
        .from_dict(context.to_dict())
    )

    assert restored == context


def test_switch_target_clears_target_scoped_semantics() -> None:
    context = SessionInvestigationContext(
        active_target="monitor",
        active_concept="service",
        active_service="nginx",
        active_path="/var/log/nginx",
        active_sources=(
            SourceConstraint.GRAFANA,
        ),
        active_excluded_sources=(
            SourceConstraint.INTERNET,
        ),
    )

    switched = context.switch_target(
        "server02"
    )

    assert switched.active_target == "server02"
    assert switched.active_concept is None
    assert switched.active_service is None
    assert switched.active_path is None
    assert switched.active_sources == ()
    assert switched.active_excluded_sources == ()


def test_requested_sentence_count_is_output_format_only() -> None:
    assert (
        SessionContextResolver
        .requested_sentence_count(
            "đúng 3 câu"
        )
        == 3
    )
    assert (
        SessionContextResolver
        .requested_sentence_count(
            "exactly 2 sentences"
        )
        == 2
    )
    assert (
        SessionContextResolver
        .requested_sentence_count(
            "briefly"
        )
        is None
    )


def test_evidence_receipt_round_trip_contains_metadata_only() -> None:
    receipt = EvidenceReceipt(
        source="linux",
        target="server-1",
        capability="system.cpu",
        fact_ids=("fact-1",),
        status="valid",
        timestamp="2026-08-23T00:00:00+00:00",
    )

    restored = EvidenceReceipt.from_dict(
        receipt.to_dict()
    )

    assert restored == receipt
    assert "raw_data" not in receipt.to_dict()
