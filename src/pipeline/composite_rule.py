from __future__ import annotations

from dataclasses import dataclass

_OPERATORS = {"gt", "ge", "lt", "le", "eq", "ne"}


@dataclass(frozen=True, slots=True)
class WeightedCondition:
    """One observable condition in a composite rule."""

    id: str
    metric: str
    operator: str
    threshold: object
    weight: float
    required: bool = True
    subject: str | None = None
    target: str | None = None
    max_age_seconds: float | None = None

    def __post_init__(self) -> None:
        if not self.id or not self.metric:
            raise ValueError("condition id and metric are required")
        if self.operator not in _OPERATORS:
            raise ValueError(f"unsupported condition operator: {self.operator}")
        if float(self.weight) <= 0:
            raise ValueError("condition weight must be positive")
        object.__setattr__(self, "weight", float(self.weight))
        if self.max_age_seconds is not None and self.max_age_seconds < 0:
            raise ValueError("max_age_seconds must be non-negative")


@dataclass(frozen=True, slots=True)
class CompositeRule:
    """Versioned weighted rule reviewed and owned by a human."""

    id: str
    type: str
    conditions: tuple[WeightedCondition, ...]
    decision_threshold: float
    severity: str
    version: str
    owner: str
    rationale: str
    source_cases: tuple[str, ...]
    minimum_coverage: float = 0.0
    renormalize_missing: bool = False

    def __post_init__(self) -> None:
        if not self.id or not self.type or not self.version:
            raise ValueError("rule id, type and version are required")
        if not self.owner or not self.rationale or not self.source_cases:
            raise ValueError("rule owner, rationale and source_cases are required")
        if not self.conditions:
            raise ValueError("composite rule requires at least one condition")
        condition_ids = [condition.id for condition in self.conditions]
        if len(condition_ids) != len(set(condition_ids)):
            raise ValueError("condition ids must be unique within a rule")
        total = sum(condition.weight for condition in self.conditions)
        threshold = float(self.decision_threshold)
        if threshold <= 0 or threshold > total:
            raise ValueError("decision_threshold must be within the total weight")
        if not 0.0 <= float(self.minimum_coverage) <= 1.0:
            raise ValueError("minimum_coverage must be between 0.0 and 1.0")
        object.__setattr__(self, "decision_threshold", threshold)
        object.__setattr__(self, "minimum_coverage", float(self.minimum_coverage))

    @property
    def total_weight(self) -> float:
        return sum(condition.weight for condition in self.conditions)
