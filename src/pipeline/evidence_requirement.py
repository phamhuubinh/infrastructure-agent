from __future__ import annotations

from dataclasses import dataclass, field

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
    timeframe: TimeRange | None = field(default=None, repr=False)
    requires_time_series: bool = field(default=False, repr=False)
    minimum_windows: int = field(default=1, repr=False)
    minimum_points: int = field(default=1, repr=False)
    requires_growth_model: bool = field(default=False, repr=False)
