from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FinalResponse:
    """
    Final response produced by the reasoning model.

    Terminates the current reasoning session.
    """

    content: str
