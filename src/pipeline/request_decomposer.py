"""Bounded deterministic decomposition for coordinated infrastructure concepts."""

from __future__ import annotations

from dataclasses import dataclass

from src.pipeline.request_frame import RequestFrame


@dataclass(frozen=True, slots=True)
class DecompositionResult:
    subframes: tuple[RequestFrame, ...]
    too_broad: bool = False
    reason: str | None = None


class RequestDecomposer:
    """Split only concepts already proven explicit by the Normalizer."""

    def __init__(self, max_subrequests: int = 4) -> None:
        if max_subrequests < 1:
            raise ValueError("max_subrequests must be positive")
        self._max_subrequests = max_subrequests

    def decompose(self, frame: RequestFrame) -> DecompositionResult:
        concepts = tuple(dict.fromkeys(frame.concepts))
        if len(concepts) <= 1:
            return DecompositionResult((frame,))
        if len(concepts) > self._max_subrequests:
            return DecompositionResult(
                (),
                too_broad=True,
                reason=(
                    f"request contains {len(concepts)} concepts; maximum is "
                    f"{self._max_subrequests}"
                ),
            )

        # Intent resolution must see only the coordinated branch's concept;
        # retaining all lexical tokens would collapse every branch back into
        # the same broad performance intent.
        subframes = tuple(
            frame.evolve(
                concepts=(concept,),
                lexical_tokens=(concept,),
                matched_synonyms=(concept, frame.operation),
                subframes=(),
            )
            for concept in concepts
        )
        return DecompositionResult(subframes)
