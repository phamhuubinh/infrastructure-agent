from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolResult:
    """
    Immutable result produced by a Tool execution.
    """

    success: bool
    data: object | None = None
    error: str | None = None
