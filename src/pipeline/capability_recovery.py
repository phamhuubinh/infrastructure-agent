from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum

from src.shared.capability import Capability
from src.shared.execution.tool_result import ToolResult
from src.tool.errors import CapabilityErrorCategory


class RecoveryStopReason(str, Enum):
    RECOVERED = "recovered"
    PRIMARY_SUCCEEDED = "primary_succeeded"
    ERROR_NOT_RECOVERABLE = "error_not_recoverable"
    TRANSPORT_FAILURE = "transport_failure"
    NO_ALTERNATIVE = "no_alternative"
    MAX_DEPTH = "max_depth"
    EXHAUSTED = "exhausted"


@dataclass(frozen=True, slots=True)
class CapabilityRecoverySpec:
    name: str
    alternatives: tuple[str, ...] = ()
    recoverable_errors: tuple[str, ...] = ()

    @classmethod
    def from_capability(cls, capability: Capability) -> CapabilityRecoverySpec:
        return cls(
            name=capability.operational_name or capability.name,
            alternatives=capability.alternatives,
            recoverable_errors=capability.recoverable_errors,
        )


@dataclass(frozen=True, slots=True)
class RecoveryAttempt:
    depth: int
    primary_capability: str
    alternative_capability: str
    error_code: str
    success: bool
    facts_recovered: tuple[str, ...]
    extra_duration_ms: float

    def to_dict(self) -> dict[str, object]:
        return {
            "depth": self.depth,
            "primary_capability": self.primary_capability,
            "alternative_capability": self.alternative_capability,
            "error_code": self.error_code,
            "success": self.success,
            "facts_recovered": list(self.facts_recovered),
            "extra_duration_ms": round(self.extra_duration_ms, 3),
        }


@dataclass(frozen=True, slots=True)
class RecoveryOutcome:
    result: ToolResult
    attempts: tuple[RecoveryAttempt, ...] = ()
    stop_reason: RecoveryStopReason = RecoveryStopReason.NO_ALTERNATIVE
    recovered_by: str | None = None

    @property
    def recovered(self) -> bool:
        return self.stop_reason is RecoveryStopReason.RECOVERED


class CapabilityRecovery:
    """Execute declared alternatives with a hard, deterministic depth bound."""

    def __init__(
        self,
        specs: Mapping[str, CapabilityRecoverySpec | Capability] | None = None,
        *,
        max_depth: int = 2,
    ) -> None:
        if max_depth < 0 or max_depth > 2:
            raise ValueError("capability recovery max_depth must be between 0 and 2")
        self.max_depth = max_depth
        self.specs = {
            name: (
                CapabilityRecoverySpec.from_capability(spec)
                if isinstance(spec, Capability)
                else spec
            )
            for name, spec in (specs or {}).items()
        }

    def recover(
        self,
        primary_capability: str,
        primary_result: ToolResult,
        execute_alternative: Callable[[str], ToolResult],
        *,
        available_capabilities: set[str] | None = None,
    ) -> RecoveryOutcome:
        if primary_result.success:
            return RecoveryOutcome(
                primary_result,
                stop_reason=RecoveryStopReason.PRIMARY_SUCCEEDED,
            )
        error = primary_result.capability_error
        if error is not None and error.category is CapabilityErrorCategory.TRANSPORT:
            # A timeout/unreachable target is target-wide. More remote commands
            # would add latency without making the transport available.
            return RecoveryOutcome(
                primary_result,
                stop_reason=RecoveryStopReason.TRANSPORT_FAILURE,
            )
        spec = self.specs.get(primary_capability)
        if spec is None or not spec.alternatives:
            return RecoveryOutcome(
                primary_result,
                stop_reason=RecoveryStopReason.NO_ALTERNATIVE,
            )
        error_code = error.code.value if error is not None else "collection_failed"
        if error_code not in spec.recoverable_errors:
            return RecoveryOutcome(
                primary_result,
                stop_reason=RecoveryStopReason.ERROR_NOT_RECOVERABLE,
            )

        attempts: list[RecoveryAttempt] = []
        visited = {primary_capability}
        queue = [
            (primary_capability, name)
            for name in spec.alternatives
            if available_capabilities is None or name in available_capabilities
        ]
        current_result = primary_result
        while queue and len(attempts) < self.max_depth:
            current_name, alternative = queue.pop(0)
            if alternative in visited:
                continue
            visited.add(alternative)
            depth = len(attempts) + 1
            started = time.perf_counter()
            result = execute_alternative(alternative)
            elapsed = (time.perf_counter() - started) * 1000.0
            current_error = current_result.capability_error
            attempts.append(
                RecoveryAttempt(
                    depth=depth,
                    primary_capability=current_name,
                    alternative_capability=alternative,
                    error_code=(
                        current_error.code.value
                        if current_error is not None
                        else "collection_failed"
                    ),
                    success=result.success,
                    facts_recovered=(
                        tuple(result.produced_fact_names) if result.success else ()
                    ),
                    extra_duration_ms=elapsed,
                )
            )
            if result.success:
                return RecoveryOutcome(
                    result=result,
                    attempts=tuple(attempts),
                    stop_reason=RecoveryStopReason.RECOVERED,
                    recovered_by=alternative,
                )
            next_error = result.capability_error
            if (
                next_error is not None
                and next_error.category is CapabilityErrorCategory.TRANSPORT
            ):
                return RecoveryOutcome(
                    result=result,
                    attempts=tuple(attempts),
                    stop_reason=RecoveryStopReason.TRANSPORT_FAILURE,
                )
            next_spec = self.specs.get(alternative)
            next_code = (
                next_error.code.value
                if next_error is not None
                else "collection_failed"
            )
            current_result = result
            if next_spec is not None and next_code in next_spec.recoverable_errors:
                queue.extend(
                    (alternative, name)
                    for name in next_spec.alternatives
                    if name not in visited
                    and (
                        available_capabilities is None
                        or name in available_capabilities
                    )
                )

        reason = (
            RecoveryStopReason.MAX_DEPTH
            if len(attempts) >= self.max_depth and self.max_depth > 0
            else RecoveryStopReason.EXHAUSTED
        )
        return RecoveryOutcome(
            result=current_result,
            attempts=tuple(attempts),
            stop_reason=reason,
        )
