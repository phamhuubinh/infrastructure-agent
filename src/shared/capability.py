from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ParameterSpec:
    """Declarative validation/binding metadata for one capability argument."""

    name: str
    source: str | None = None
    required: bool = False
    value_type: str = "str"
    default: object | None = None
    has_default: bool = False
    enum: tuple[object, ...] = ()
    pattern: str | None = None
    minimum: float | None = None
    maximum: float | None = None


@dataclass(frozen=True, slots=True)
class Capability:
    name: str
    handler: Callable[..., Any]
    category: str = "other"
    intents: tuple[str, ...] = ()
    related: tuple[str, ...] = ()
    covers: tuple[str, ...] = ()
    operational_name: str = ""
    description: str = ""
    supported_targets: tuple[str, ...] = ()
    parameters: tuple[str, ...] = ()
    parameter_specs: tuple[ParameterSpec, ...] = ()
    preconditions: tuple[str, ...] = ()
    required_binaries: tuple[str, ...] = ()
    required_any_binaries: tuple[str, ...] = ()
    optional_binaries: tuple[str, ...] = ()
    supported_init_systems: tuple[str, ...] = ()
    estimated_cost: float = 0.0
    expected_reliability: float = 1.0
    produces_facts: tuple[str, ...] = ()
    alternatives: tuple[str, ...] = ()
    recoverable_errors: tuple[str, ...] = ()
    mutation_risk: str = "none"

    def __post_init__(self) -> None:
        if self.estimated_cost < 0:
            raise ValueError("estimated_cost must be non-negative")
        if not 0.0 <= self.expected_reliability <= 1.0:
            raise ValueError("expected_reliability must be between 0.0 and 1.0")
        if self.mutation_risk not in {"none", "low", "medium", "high"}:
            raise ValueError("mutation_risk must be none, low, medium, or high")
        if self.name in self.alternatives:
            raise ValueError("capability cannot declare itself as an alternative")
