from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.shared.execution.command_result import CommandResult
from src.tool.capability_result import CapabilityResult, CapabilityStatus


@dataclass(frozen=True, slots=True)
class ToolResult:
    """
    Immutable result produced by a Tool execution.
    """

    success: bool
    data: Any = None
    error: str | None = None
    capability_status: CapabilityStatus | None = None
    command_results: tuple[CommandResult, ...] = ()
    warnings: tuple[str, ...] = ()
    produced_fact_names: tuple[str, ...] = ()

    @classmethod
    def from_capability_result(cls, result: CapabilityResult) -> ToolResult:
        return cls(
            success=result.success,
            data=result.data,
            error=result.error,
            capability_status=result.status,
            command_results=result.command_results,
            warnings=result.warnings,
            produced_fact_names=result.produced_fact_names,
        )
