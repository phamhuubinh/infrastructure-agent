from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from src.shared.execution.command_result import CommandResult


class CapabilityStatus(str, Enum):
    """Validity/collection outcome of one capability execution."""

    VALID = "valid"
    VALID_EMPTY = "valid_empty"
    PARTIAL = "partial"
    COLLECTION_FAILED = "collection_failed"
    UNSUPPORTED = "unsupported"
    INVALID_PARAMETERS = "invalid_parameters"
    PARSE_FAILED = "parse_failed"


def _is_empty(data: Any) -> bool:
    return data is None or data == "" or data == {} or data == [] or data == ()


@dataclass(frozen=True, slots=True)
class CapabilityResult:
    """Structured result produced by a Child Tool capability handler."""

    status: CapabilityStatus
    data: Any = None
    command_results: tuple[CommandResult, ...] = ()
    warnings: tuple[str, ...] = ()
    produced_fact_names: tuple[str, ...] = ()
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.status in (CapabilityStatus.VALID, CapabilityStatus.VALID_EMPTY)

    @property
    def is_valid(self) -> bool:
        return self.success

    @classmethod
    def from_legacy(
        cls,
        data: Any,
        *,
        command_results: tuple[CommandResult, ...] = (),
        warnings: tuple[str, ...] = (),
        produced_fact_names: tuple[str, ...] = (),
    ) -> CapabilityResult:
        """Wrap a legacy handler payload without hiding command failures."""

        failed = tuple(result for result in command_results if not result.success)
        succeeded = tuple(result for result in command_results if result.success)
        if failed:
            first = failed[0]
            error = (
                f"Command collection failed: {first.status.value}"
                f" (command_id={first.command_id})"
            )
            if succeeded and not _is_empty(data):
                return cls(
                    status=CapabilityStatus.PARTIAL,
                    data=data,
                    command_results=command_results,
                    warnings=warnings,
                    produced_fact_names=produced_fact_names,
                    error=error,
                )
            return cls(
                status=CapabilityStatus.COLLECTION_FAILED,
                data=None,
                command_results=command_results,
                warnings=warnings,
                produced_fact_names=(),
                error=error,
            )

        return cls(
            status=(
                CapabilityStatus.VALID_EMPTY if _is_empty(data) else CapabilityStatus.VALID
            ),
            data=data,
            command_results=command_results,
            warnings=warnings,
            produced_fact_names=produced_fact_names,
        )
