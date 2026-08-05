from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta

from src.pipeline.fact import Fact, FactValidity, thaw
from src.pipeline.fact_set import FactSet


@dataclass(frozen=True, slots=True)
class MetricTolerance:
    absolute: float = 0.0
    relative: float = 0.0

    def accepts(self, left: float, right: float) -> bool:
        difference = abs(left - right)
        scale = max(abs(left), abs(right), 1.0)
        return difference <= max(self.absolute, self.relative * scale)


@dataclass(frozen=True, slots=True)
class Contradiction:
    metric: str
    target: str
    subject: str
    fact_ids: tuple[str, ...]
    sources: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "metric": self.metric,
            "target": self.target,
            "subject": self.subject,
            "fact_ids": list(self.fact_ids),
            "sources": list(self.sources),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    fact_set: FactSet
    contradictions: tuple[Contradiction, ...] = ()

    @property
    def contradictory(self) -> bool:
        return bool(self.contradictions)


class FactReconciler:
    """Surface incompatible same-window facts without silently overwriting."""

    def __init__(
        self,
        *,
        tolerances: dict[str, MetricTolerance | tuple[float, float]] | None = None,
        source_reliability: dict[str, float] | None = None,
        window_seconds: float = 60.0,
    ) -> None:
        self._tolerances: dict[str, MetricTolerance] = {}
        for metric, tolerance in (tolerances or {}).items():
            self._tolerances[metric] = (
                tolerance
                if isinstance(tolerance, MetricTolerance)
                else MetricTolerance(*tolerance)
            )
        self._source_reliability = dict(source_reliability or {})
        self._window = timedelta(seconds=max(window_seconds, 0.0))

    def reconcile(self, facts: FactSet | Iterable[Fact]) -> ReconciliationResult:
        fact_set = facts if isinstance(facts, FactSet) else FactSet(tuple(facts))
        groups: dict[tuple[str, str, str], list[Fact]] = {}
        for fact in fact_set:
            if fact.validity is not FactValidity.VALID:
                continue
            groups.setdefault((fact.metric, fact.target, fact.subject), []).append(fact)

        contradictory_ids: set[str] = set()
        contradictions: list[Contradiction] = []
        for (metric, target, subject), group in sorted(groups.items()):
            ordered = sorted(
                group, key=lambda item: (item.observed_at, item.source, item.id)
            )
            for index, left in enumerate(ordered):
                incompatible = [left]
                for right in ordered[index + 1 :]:
                    if right.observed_at - left.observed_at > self._window:
                        break
                    if left.source == right.source:
                        continue
                    if not self._equivalent(metric, left.value, right.value):
                        incompatible.append(right)
                if len(incompatible) < 2:
                    continue
                ids = tuple(sorted(fact.id for fact in incompatible))
                if set(ids).issubset(contradictory_ids):
                    continue
                contradictory_ids.update(ids)
                ranked_sources = tuple(
                    sorted(
                        {fact.source for fact in incompatible},
                        key=lambda source: (
                            -self._source_reliability.get(source, 0.0),
                            source,
                        ),
                    )
                )
                contradictions.append(
                    Contradiction(
                        metric=metric,
                        target=target,
                        subject=subject,
                        fact_ids=ids,
                        sources=ranked_sources,
                        reason=(
                            "same-window values exceed configured tolerance; "
                            "all observations are retained"
                        ),
                    )
                )

        if not contradictory_ids:
            return ReconciliationResult(fact_set)
        reconciled = FactSet(
            tuple(
                fact.as_contradictory() if fact.id in contradictory_ids else fact
                for fact in fact_set
            )
        )
        return ReconciliationResult(reconciled, tuple(contradictions))

    def _equivalent(self, metric: str, left: object, right: object) -> bool:
        if (
            isinstance(left, (int, float))
            and not isinstance(left, bool)
            and isinstance(right, (int, float))
            and not isinstance(right, bool)
        ):
            tolerance = self._tolerances.get(metric, MetricTolerance())
            return tolerance.accepts(float(left), float(right))
        return thaw(left) == thaw(right)
