from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Observation:
    """
    Immutable observation collected from the environment.

    Carries the Action (tool + arguments) that produced it, so a sequence
    of Observations is self-describing without relying on prompt prose.
    """

    data: object
    success: bool = True
    error: str | None = None
    tool: str = ""
    arguments: dict[str, object] = field(default_factory=dict)
