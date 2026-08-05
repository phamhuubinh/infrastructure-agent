from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.shared.execution.command_result import CommandResult
from src.tool.capability_result import CapabilityResult, CapabilityStatus
from src.tool.errors import CapabilityError, capability_error_from_status


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
    capability_error: CapabilityError | None = None
    security_inspected: bool = False
    security_allowed: bool = False
    security_inspectors: tuple[str, ...] = ()
    source: str | None = None
    source_kind: str | None = None
    resource: str | None = None
    parameters: tuple[tuple[str, object], ...] = ()
    schema_version: str = "legacy"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "parameters",
            tuple(sorted((str(key), value) for key, value in self.parameters)),
        )
        if self.capability_error is None and not self.success:
            status = (
                self.capability_status.value
                if self.capability_status is not None
                else CapabilityStatus.COLLECTION_FAILED.value
            )
            object.__setattr__(
                self,
                "capability_error",
                capability_error_from_status(
                    status,
                    command_results=self.command_results,
                    message=self.error,
                ),
            )

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
            capability_error=result.capability_error,
        )
