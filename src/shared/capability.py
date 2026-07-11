from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Capability:
    name: str
    handler: Callable[..., dict[str, object]]
    category: str = "other"
    intents: tuple[str, ...] = ()
    related: tuple[str, ...] = ()
    covers: tuple[str, ...] = ()
