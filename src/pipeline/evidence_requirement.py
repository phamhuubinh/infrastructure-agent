from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from src.pipeline.fact import FactValidity
from src.pipeline.time_range_resolver import TimeRange


@dataclass(frozen=True, slots=True)
class EvidenceRequirement:
    """One required piece of operational evidence.

    Describes **what** evidence must be collected, not **how** to collect it.

    Attributes:
        name: The evidence category name (e.g. "CPU", "Services", "Firewall").
        required: True if this evidence must always be collected before
                  assessment. False if it is optional and collected only
                  when additional confidence or validation is needed.
        category: Optional grouping category for organization purposes.
    """

    name: str
    required: bool = True
    category: str = ""
    metric: str = field(default="", repr=False)
    target: str | None = field(default=None, repr=False)
    subject: str | None = field(default=None, repr=False)
    parameter_scope: Mapping[str, object] = field(
        default_factory=lambda: MappingProxyType({}), repr=False
    )
    accepted_validities: tuple[FactValidity, ...] = field(
        default=(FactValidity.VALID, FactValidity.VALID_EMPTY), repr=False
    )
    max_age_seconds: float | None = field(default=None, repr=False)
    allow_stale: bool = field(default=False, repr=False)
    timeframe: TimeRange | None = field(default=None, repr=False)
    requires_time_series: bool = field(default=False, repr=False)
    minimum_windows: int = field(default=1, repr=False)
    minimum_points: int = field(default=1, repr=False)
    requires_growth_model: bool = field(default=False, repr=False)

    def __post_init__(self) -> None:
        scope = self.parameter_scope
        if isinstance(scope, dict):
            scope = MappingProxyType(dict(scope))
        elif isinstance(scope, (tuple, list)):
            scope = MappingProxyType(dict(scope))
        elif not isinstance(scope, MappingProxyType):
            raise TypeError("parameter_scope must be a mapping or key/value pairs")
        object.__setattr__(self, "parameter_scope", scope)
        validities = tuple(
            item if isinstance(item, FactValidity) else FactValidity(str(item))
            for item in self.accepted_validities
        )
        object.__setattr__(self, "accepted_validities", validities)
        if self.max_age_seconds is not None and self.max_age_seconds < 0:
            raise ValueError("max_age_seconds must be non-negative")
