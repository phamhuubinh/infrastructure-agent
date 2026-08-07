"""DR1-705: Numeric and unit consistency validator.

Checks that facts sharing a subject/target/observation window are
arithmetically consistent (e.g. filesystem total ~= used + available) so the
model is not left to reconcile ambiguous fields itself, and detects when the
same metric was reported with two different values in one investigation
(the "154 GB then 391.8 GB" class of bug).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from src.pipeline.fact import Fact

_RELATIVE_TOLERANCE = 0.02  # 2%: filesystem reserved blocks etc.

# (total_metric, used_metric, free_metric) triples that must sum consistently.
_CONSISTENCY_TRIPLES: tuple[tuple[str, str, str], ...] = (
    ("filesystem.size_bytes", "filesystem.used_bytes", "filesystem.available_bytes"),
    ("memory.total_bytes", "memory.used_bytes", "memory.available_bytes"),
)


@dataclass(frozen=True, slots=True)
class NumericInconsistency:
    kind: str
    subject: str
    target: str
    detail: str


def _numeric(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _group_by_subject_target(facts: tuple[Fact, ...]) -> dict[tuple[str, str], list[Fact]]:
    groups: dict[tuple[str, str], list[Fact]] = defaultdict(list)
    for fact in facts:
        if fact.usable:
            groups[(fact.subject, fact.target)].append(fact)
    return groups


def find_arithmetic_inconsistencies(
    facts: tuple[Fact, ...],
) -> tuple[NumericInconsistency, ...]:
    """Flag total/used/available triples that do not add up within tolerance."""

    issues: list[NumericInconsistency] = []
    groups = _group_by_subject_target(facts)
    for (subject, target), group in groups.items():
        by_metric = {fact.metric: fact for fact in group}
        for total_key, used_key, free_key in _CONSISTENCY_TRIPLES:
            total = by_metric.get(total_key)
            used = by_metric.get(used_key)
            free = by_metric.get(free_key)
            if total is None or used is None or free is None:
                continue
            total_v, used_v, free_v = (
                _numeric(total.value),
                _numeric(used.value),
                _numeric(free.value),
            )
            if total_v is None or used_v is None or free_v is None or total_v <= 0:
                continue
            diff = abs(total_v - (used_v + free_v))
            if diff / total_v > _RELATIVE_TOLERANCE:
                issues.append(
                    NumericInconsistency(
                        kind="arithmetic_mismatch",
                        subject=subject,
                        target=target,
                        detail=(
                            f"{total_key}={total_v} != {used_key}={used_v} + "
                            f"{free_key}={free_v} (tolerance {_RELATIVE_TOLERANCE:.0%})"
                        ),
                    )
                )
    return tuple(issues)


def find_duplicate_metric_conflicts(
    facts: tuple[Fact, ...],
) -> tuple[NumericInconsistency, ...]:
    """Flag the same (subject, target, metric) reported with different values."""

    issues: list[NumericInconsistency] = []
    seen: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for fact in facts:
        if not fact.usable:
            continue
        key = (fact.subject, fact.target, fact.metric)
        seen[key].add(str(fact.value))
    for (subject, target, metric), values in seen.items():
        if len(values) > 1:
            issues.append(
                NumericInconsistency(
                    kind="duplicate_metric_conflict",
                    subject=subject,
                    target=target,
                    detail=f"{metric} reported as {sorted(values)}",
                )
            )
    return tuple(issues)


def validate_numeric_consistency(
    facts: tuple[Fact, ...],
) -> tuple[NumericInconsistency, ...]:
    """Run all numeric consistency checks and return combined issues."""

    return (
        *find_arithmetic_inconsistencies(facts),
        *find_duplicate_metric_conflicts(facts),
    )
