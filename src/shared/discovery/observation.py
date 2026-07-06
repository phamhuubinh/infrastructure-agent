from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Observation:
    """
    Immutable observation collected from the environment.
    """

    data: object
    success: bool = True
    error: str | None = None
