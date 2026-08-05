from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType

from src.pipeline.fact import Fact, FactValidity, utc_datetime


def _sort_key(fact: Fact) -> tuple[object, ...]:
    return (
        fact.metric,
        fact.target,
        fact.subject,
        fact.observed_at,
        fact.source,
        fact.id,
    )


@dataclass(frozen=True, slots=True)
class FactSet:
    """Per-investigation immutable fact collection with deterministic indexes."""

    facts: tuple[Fact, ...] = ()
    _by_metric: MappingProxyType = field(init=False, repr=False, compare=False)
    _by_target: MappingProxyType = field(init=False, repr=False, compare=False)
    _by_validity: MappingProxyType = field(init=False, repr=False, compare=False)
    _by_source: MappingProxyType = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        deduplicated: dict[str, Fact] = {}
        for fact in self.facts:
            current = deduplicated.get(fact.id)
            if current is not None and current != fact:
                raise ValueError(f"fact id collision: {fact.id}")
            deduplicated[fact.id] = fact
        ordered = tuple(sorted(deduplicated.values(), key=_sort_key))
        object.__setattr__(self, "facts", ordered)
        object.__setattr__(self, "_by_metric", self._index(ordered, "metric"))
        object.__setattr__(self, "_by_target", self._index(ordered, "target"))
        object.__setattr__(self, "_by_validity", self._index(ordered, "validity"))
        object.__setattr__(self, "_by_source", self._index(ordered, "source"))

    @staticmethod
    def _index(facts: tuple[Fact, ...], attribute: str) -> MappingProxyType:
        values: dict[object, list[Fact]] = {}
        for fact in facts:
            values.setdefault(getattr(fact, attribute), []).append(fact)
        return MappingProxyType({key: tuple(items) for key, items in values.items()})

    @classmethod
    def merge(cls, *collections: Iterable[Fact] | FactSet) -> FactSet:
        facts: list[Fact] = []
        for collection in collections:
            facts.extend(
                collection.facts if isinstance(collection, FactSet) else collection
            )
        return cls(tuple(facts))

    def append(self, *facts: Fact) -> FactSet:
        return FactSet.merge(self, facts)

    def by_metric(self, metric: str) -> tuple[Fact, ...]:
        return self._by_metric.get(metric, ())

    def by_target(self, target: str) -> tuple[Fact, ...]:
        return self._by_target.get(target, ())

    def by_validity(self, validity: FactValidity) -> tuple[Fact, ...]:
        return self._by_validity.get(validity, ())

    def by_source(self, source: str) -> tuple[Fact, ...]:
        return self._by_source.get(source, ())

    def query(
        self,
        *,
        metric: str | None = None,
        target: str | None = None,
        validity: FactValidity | tuple[FactValidity, ...] | None = None,
        source: str | None = None,
        subject: str | None = None,
        start: datetime | int | float | str | None = None,
        end: datetime | int | float | str | None = None,
    ) -> tuple[Fact, ...]:
        candidates = self.facts
        if metric is not None:
            candidates = self.by_metric(metric)
        allowed = (validity,) if isinstance(validity, FactValidity) else validity
        start_at = utc_datetime(start) if start is not None else None
        end_at = utc_datetime(end) if end is not None else None
        return tuple(
            fact
            for fact in candidates
            if (target is None or fact.target == target)
            and (allowed is None or fact.validity in allowed)
            and (source is None or fact.source == source)
            and (subject is None or fact.subject == subject)
            and (start_at is None or fact.observed_at >= start_at)
            and (end_at is None or fact.observed_at <= end_at)
        )

    def to_dict(self) -> dict[str, object]:
        return {"facts": [fact.to_dict() for fact in self.facts], "count": len(self)}

    def __iter__(self):
        return iter(self.facts)

    def __len__(self) -> int:
        return len(self.facts)


class FactSetBuilder:
    """Append-only mutable builder whose output is an immutable FactSet."""

    def __init__(self) -> None:
        self._facts: list[Fact] = []

    def add(self, fact: Fact) -> FactSetBuilder:
        self._facts.append(fact)
        return self

    def add_many(self, facts: Iterable[Fact]) -> FactSetBuilder:
        self._facts.extend(facts)
        return self

    def build(self) -> FactSet:
        return FactSet(tuple(self._facts))
