from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


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
    estimated_cost: float = 0.0
    mutation_risk: str = "none"
