from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ToolResult:
    """
    Immutable result produced by a Tool execution.
    """

    success: bool
    data: Any = None
    error: str | None = None
