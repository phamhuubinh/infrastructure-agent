"""GA2-C10 — Deterministic ordered multi-intent planning.

A sequenced request such as ``Giải thích RAM là gì rồi kiểm tra RAM trên
monitor`` or ``Tìm phiên bản hiện tại rồi tạo config dùng phiên bản đó``
must not collapse into a single generic infra assessment honouring only the
last noun phrase.  This module detects explicit sequencing conjunctions and
produces ordered step plans that preserve:

- step order,
- target per step,
- source constraints per step,
- dependencies between steps,
- fail-closed behavior when an earlier dependent step is unresolved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto

from src.pipeline.request_frame import RequestFrame
from src.pipeline.request_semantics import SourceConstraint


class StepKind(Enum):
    """The deterministic role of one ordered step."""

    EXPLAIN = auto()  # stable knowledge explanation
    INSPECT = auto()  # live environment read-only fact
    EXTERNAL = auto()  # current external verification
    GENERATE = auto()  # content generation
    COMPARE = auto()  # multi-source comparison


@dataclass(frozen=True, slots=True)
class PlannedStep:
    """One ordered step with its own semantics and dependency contract."""

    order: int
    kind: StepKind
    concepts: tuple[str, ...]
    source_constraints: tuple[SourceConstraint, ...] = (SourceConstraint.ANY,)
    target_raw: str | None = None
    depends_on: tuple[int, ...] = ()
    note: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "order": self.order,
            "kind": self.kind.name,
            "concepts": list(self.concepts),
            "source_constraints": [source.name for source in self.source_constraints],
            "target_raw": self.target_raw,
            "depends_on": list(self.depends_on),
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class MultiIntentPlan:
    """Deterministic ordered plan for a sequenced compound request."""

    steps: tuple[PlannedStep, ...]
    source: str = "sequenced_markers"

    @property
    def ordered(self) -> bool:
        return True

    def to_dict(self) -> dict[str, object]:
        return {"steps": [step.to_dict() for step in self.steps], "source": self.source}


class MultiIntentPlanner:
    """Detect explicit sequencing and build a deterministic ordered plan."""

    # Conjunctions that explicitly sequence two intents ("rồi", "sau đó",
    # "then", "first ... then ...").  A bare "và/and" stays with the existing
    # coordinated de-composer (GA2-C05/DR1-405).
    _SEQUENCED = re.compile(
        r"\b(?:rồi|roi|sau\s+đó|sau\s+do|sau\s+này|sau\s+nay|"
        r"tiếp\s+theo|tiep\s+theo|then|and\s+then|"
        r"sau\s+khi|sau\s+khi\s+kiểm\s+tra|before|trước\s+khi)\b",
        re.IGNORECASE,
    )
    _COMPARE = re.compile(
        r"\b(?:so\s+sánh|so\s+sanh|compare|comparison)\b", re.IGNORECASE
    )
    _EXPLAIN = re.compile(
        r"\b(?:giải\s+thích|giai\s+thich|explain|what\s+is|nghĩa\s+là|định\s+nghĩa)\b",
        re.IGNORECASE,
    )
    _CURRENT_EXTERNAL = re.compile(
        r"\b(?:phiên\s+bản|phien\s+ban|version|mới\s+nhất|moi\s+nhat|latest|"
        r"current|hiện\s+tại|hien\s+tai|giá|price|release)\b",
        re.IGNORECASE,
    )

    def plan(self, frame: RequestFrame) -> MultiIntentPlan | None:
        """Return a deterministic ordered plan only for explicit sequencing.

        Returns ``None`` for coordinated (non-sequenced) requests so the
        existing ``RequestDecomposer`` contract remains authoritative.
        """
        raw = frame.raw_request.casefold()
        if not self._SEQUENCED.search(raw):
            return None

        # Explanation + live check: "Giải thích RAM là gì rồi kiểm tra RAM
        # trên monitor."
        if self._EXPLAIN.search(raw) and (
            "kiểm tra" in raw or "kiem tra" in raw or "check" in raw
        ):
            return self._explain_then_inspect(frame, raw)

        # Current external + generation: "Tìm phiên bản hiện tại rồi tạo
        # config dùng phiên bản đó."
        if self._CURRENT_EXTERNAL.search(raw) and self._generation_marker(raw):
            return self._external_then_generate(frame, raw)

        return None

    @staticmethod
    def _generation_marker(raw: str) -> bool:
        return any(
            marker in raw
            for marker in ("viết", "viet", "tạo", "tao", "write", "generate", "create")
        )

    def split_sequenced_clauses(self, raw_request: str) -> tuple[str, str] | None:
        """Split a sequenced compound request into its two ordered clauses.

        Returns ``None`` when no explicit sequencing marker is present, or
        when either side of the split is empty. The runtime uses this to
        route each half of an EXPLAIN-then-INSPECT plan through the exact
        same single-shot handling (``chat`` / ``run_with_steps``) that
        clause would receive standalone, instead of re-deriving new
        natural-language phrasing per step kind.
        """
        match = self._SEQUENCED.search(raw_request)
        if match is None:
            return None
        first = raw_request[: match.start()].strip(" ,.;")
        second = raw_request[match.end() :].strip(" ,.;")
        if not first or not second:
            return None
        return first, second

    def _concepts_suffix(self, raw: str) -> tuple[str, ...]:
        # Take the last infra-looking noun phrase as the step concept.
        for token in (
            "cpu",
            "ram",
            "memory",
            "disk",
            "filesystem",
            "network",
            "service",
        ):
            if token in raw:
                return (token,)
        return ("machine",)

    def _explain_then_inspect(self, frame: RequestFrame, raw: str) -> MultiIntentPlan:
        concepts = self._concepts_suffix(raw)
        return MultiIntentPlan(
            steps=(
                PlannedStep(
                    order=1,
                    kind=StepKind.EXPLAIN,
                    concepts=concepts,
                    note="stable-knowledge explanation",
                ),
                PlannedStep(
                    order=2,
                    kind=StepKind.INSPECT,
                    concepts=concepts,
                    source_constraints=frame.source_constraints,
                    target_raw=frame.target_raw,
                    depends_on=(),
                    note="live environment fact",
                ),
            )
        )

    def _external_then_generate(self, frame: RequestFrame, raw: str) -> MultiIntentPlan:
        concepts = self._concepts_suffix(raw)
        return MultiIntentPlan(
            steps=(
                PlannedStep(
                    order=1,
                    kind=StepKind.EXTERNAL,
                    concepts=concepts,
                    source_constraints=(SourceConstraint.INTERNET,),
                    depends_on=(),
                    note="current external verification",
                ),
                PlannedStep(
                    order=2,
                    kind=StepKind.GENERATE,
                    concepts=concepts,
                    source_constraints=frame.source_constraints,
                    depends_on=(1,),
                    note="content generation depends on verified current value",
                ),
            )
        )


__all__ = ["MultiIntentPlan", "MultiIntentPlanner", "PlannedStep", "StepKind"]
