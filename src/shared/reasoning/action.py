from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Action:
    """
    A single action requested by the reasoning model.
    """

    tool: str
    arguments: dict[str, object]
