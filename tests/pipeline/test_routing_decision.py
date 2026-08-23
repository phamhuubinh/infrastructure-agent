from __future__ import annotations

import pytest

from src.pipeline.request_frame import (
    RequestFrame,
)
from src.pipeline.routing_decision import (
    EvidenceStatus,
    RoutingClarificationError,
    RoutingDecision,
    RoutingStatus,
)


def test_resolved_property_requires_resolved_status() -> None:
    frame = RequestFrame(
        raw_request="hello"
    )

    resolved = RoutingDecision(
        RoutingStatus.RESOLVED,
        frame,
    )

    clarify = RoutingDecision(
        RoutingStatus
        .CLARIFICATION_REQUIRED,
        frame,
    )

    assert resolved.resolved is True
    assert clarify.resolved is False


def test_clarification_error_preserves_decision() -> None:
    frame = RequestFrame(
        raw_request="check it"
    )

    decision = RoutingDecision(
        status=(
            RoutingStatus
            .CLARIFICATION_REQUIRED
        ),
        request_frame=frame,
        reason="target required",
        missing_field="target",
    )

    error = RoutingClarificationError(
        decision
    )

    assert error.decision is decision
    assert str(error) == "target required"


def test_evidence_status_taxonomy_is_explicit() -> None:
    assert (
        EvidenceStatus.SUFFICIENT
        is not EvidenceStatus.UNAVAILABLE
    )
