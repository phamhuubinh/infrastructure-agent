"""DR1-802 — curated routing-stage regression matrix.

These tests intentionally inspect candidates, score/margin, and routing
status; asserting only the final intent would hide a false-positive route.
"""

from __future__ import annotations

import pytest

from src.pipeline.intent_resolver import Intent, IntentResolver
from src.pipeline.normalizer import Normalizer
from src.pipeline.routing_decision import RoutingStatus
from src.pipeline.target_resolver import TargetResolver, UnknownTargetError
from src.tool.target_registry import TargetRegistry


@pytest.mark.parametrize(
    ("user_request", "concept", "operation", "intent"),
    [
        ("Kiem tra CPU", "cpu", "inspect", Intent.CPU_ASSESSMENT),
        ("sevice nao bi loi", "service", "diagnose", Intent.SERVICE_ASSESSMENT),
        (
            "Check giúp RAM của server hộ cái",
            "memory",
            "inspect",
            Intent.MEMORY_ASSESSMENT,
        ),
        ("kernl version?", "kernel", "inspect", Intent.MACHINE_ASSESSMENT),
        (
            "web bị ì, debug giúp",
            "performance",
            "diagnose",
            Intent.PERFORMANCE_ASSESSMENT,
        ),
    ],
)
def test_multilingual_typo_and_code_switch_stage_contract(
    user_request: str,
    concept: str,
    operation: str,
    intent: Intent,
) -> None:
    frame = Normalizer().normalize(user_request)
    resolution = IntentResolver().resolve_frame(frame)

    assert frame.concepts == (concept,)
    assert frame.operation == operation
    candidate = next(item for item in frame.concept_candidates if item.label == concept)
    assert candidate.score >= 0.72
    assert resolution.intent is intent
    assert resolution.candidates[0].intent is intent
    assert resolution.score >= resolution.candidates[-1].score
    assert resolution.ambiguity_margin is not None
    assert resolution.routing_status is RoutingStatus.RESOLVED


def test_unknown_input_requires_clarification_instead_of_a_false_positive() -> None:
    frame = Normalizer().normalize("blah blah nothing relevant")
    resolution = IntentResolver().resolve_frame(frame)

    assert frame.concepts == ("machine",)
    assert frame.confidence == 0.0
    assert resolution.routing_status is RoutingStatus.CLARIFICATION_REQUIRED
    assert resolution.ambiguity_margin is not None


def test_explicit_unknown_target_does_not_fall_back_to_localhost() -> None:
    resolver = TargetResolver(TargetRegistry())
    frame = Normalizer().normalize("Kiểm tra CPU trên unknown-db-999")

    with pytest.raises(UnknownTargetError):
        resolver.resolve_frame(frame)
