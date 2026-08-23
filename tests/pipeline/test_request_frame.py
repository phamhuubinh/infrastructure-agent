from __future__ import annotations

from src.pipeline.request_frame import (
    RequestFrame,
)
from src.pipeline.request_semantics import (
    ExecutionIntent,
    ExternalNeed,
    InformationScope,
    RequestDomain,
    SourceConstraint,
)


def test_frame_defaults_are_safe_and_non_executable() -> None:
    frame = RequestFrame(
        raw_request="hello"
    )

    assert frame.target_resolved is None
    assert frame.concepts == ()
    assert frame.source_constraints == (
        SourceConstraint.ANY,
    )


def test_frame_evolve_preserves_original() -> None:
    original = RequestFrame(
        raw_request="inspect cpu"
    )

    resolved = original.evolve(
        target_resolved="server-1",
        concepts=("cpu",),
    )

    assert original.target_resolved is None
    assert resolved.target_resolved == (
        "server-1"
    )
    assert resolved.concepts == ("cpu",)


def test_frame_serialization_uses_typed_semantics() -> None:
    frame = RequestFrame(
        raw_request="read current page",
        request_domain=(
            RequestDomain
            .EXTERNAL_INFORMATION
        ),
        information_scope=(
            InformationScope.EXPLICIT_URL
        ),
        external_need=ExternalNeed.URL,
        source_constraints=(
            SourceConstraint.URL_ONLY,
        ),
        execution_intent=(
            ExecutionIntent.EXPLAIN
        ),
        explicit_url=(
            "https://example.com"
        ),
    )

    payload = frame.to_dict()

    assert payload["request_domain"] == (
        "EXTERNAL_INFORMATION"
    )
    assert payload["external_need"] == "URL"
