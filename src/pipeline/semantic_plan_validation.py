"""Typed validation result contract between semantic planning and execution."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import Enum

from src.pipeline.semantic_plan import SemanticPlan
from src.shared.execution.command_result import redact_sensitive

MAX_VALIDATION_TRACE_TEXT = 256
_FIELD_NAME = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_TraceScalar = str | int | float | bool | None


class SemanticPlanValidationStatus(str, Enum):
    VALID = "valid"
    CLARIFY = "clarify"
    REJECT = "reject"
    UNAVAILABLE = "unavailable"


class SemanticPlanValidationReason(str, Enum):
    """Stable reason codes for harness branching without string parsing."""

    VALID = "valid"
    MALFORMED_PLAN = "malformed_plan"
    PLANNER_UNCERTAIN = "planner_uncertain"
    REQUEST_CONFLICT = "request_conflict"
    TARGET_MISSING = "target_missing"
    TARGET_UNKNOWN = "target_unknown"
    TARGET_AMBIGUOUS = "target_ambiguous"
    SOURCE_CONFLICT = "source_conflict"
    SOURCE_FORBIDDEN = "source_forbidden"
    SOURCE_UNAVAILABLE = "source_unavailable"
    FRESHNESS_UNVERIFIED = "freshness_unverified"
    FRESHNESS_UNAVAILABLE = "freshness_unavailable"
    MUTATION_UNSAFE = "mutation_unsafe"
    CAPABILITY_UNKNOWN = "capability_unknown"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    CAPABILITY_SOURCE_MISMATCH = "capability_source_mismatch"
    PARAMETER_MISSING = "parameter_missing"
    PARAMETER_INVALID = "parameter_invalid"
    COMPUTE_MISSING = "compute_missing"
    COMPUTE_INVALID = "compute_invalid"
    COMPUTE_CONFLICT = "compute_conflict"


@dataclass(frozen=True, slots=True)
class SemanticPlanValidationValue:
    """One explicit, bounded original-to-normalized trace value."""

    field: str
    original: _TraceScalar
    normalized: _TraceScalar

    def __post_init__(self) -> None:
        if not _FIELD_NAME.fullmatch(self.field):
            raise ValueError("Validation value field is invalid.")
        _validate_trace_scalar(self.original, "original")
        _validate_trace_scalar(self.normalized, "normalized")

    @classmethod
    def safe(
        cls,
        field: str,
        *,
        original: _TraceScalar,
        normalized: _TraceScalar,
    ) -> SemanticPlanValidationValue:
        return cls(
            field=field,
            original=_safe_trace_scalar(original),
            normalized=_safe_trace_scalar(normalized),
        )

    def to_trace_dict(self) -> dict[str, _TraceScalar]:
        return {
            "field": self.field,
            "original": self.original,
            "normalized": self.normalized,
        }


@dataclass(frozen=True, slots=True)
class SemanticPlanValidationResult:
    """Immutable gate result; only ``VALID`` exposes an executable plan.

    If validation normalizes a plan, it must provide explicit value records.
    This prevents a changed plan from being silently substituted for the
    planner's original proposal.
    """

    status: SemanticPlanValidationStatus
    reason: SemanticPlanValidationReason
    original_plan: SemanticPlan | None = None
    validated_plan: SemanticPlan | None = None
    values: tuple[SemanticPlanValidationValue, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, SemanticPlanValidationStatus):
            raise TypeError("Validation status must be SemanticPlanValidationStatus.")
        if not isinstance(self.reason, SemanticPlanValidationReason):
            raise TypeError("Validation reason must be SemanticPlanValidationReason.")
        if self.original_plan is not None and not isinstance(
            self.original_plan, SemanticPlan
        ):
            raise TypeError("original_plan must be a SemanticPlan or None.")
        if self.validated_plan is not None and not isinstance(
            self.validated_plan, SemanticPlan
        ):
            raise TypeError("validated_plan must be a SemanticPlan or None.")
        if not isinstance(self.values, tuple) or any(
            not isinstance(value, SemanticPlanValidationValue) for value in self.values
        ):
            raise TypeError("values must be a tuple of validation values.")
        if self.status is SemanticPlanValidationStatus.VALID:
            if self.reason is not SemanticPlanValidationReason.VALID:
                raise ValueError("VALID status requires the VALID reason.")
            if self.original_plan is None or self.validated_plan is None:
                raise ValueError("VALID status requires original and validated plans.")
        elif self.validated_plan is not None:
            raise ValueError("Only VALID results may expose a validated plan.")
        if (
            self.original_plan is not None
            and self.validated_plan is not None
            and self.original_plan != self.validated_plan
            and not self.values
        ):
            raise ValueError("Plan normalization requires explicit trace values.")
        fields = [value.field for value in self.values]
        if len(fields) != len(set(fields)):
            raise ValueError("Validation trace fields must be unique.")

    @property
    def can_execute(self) -> bool:
        return self.status is SemanticPlanValidationStatus.VALID

    @classmethod
    def valid(
        cls,
        plan: SemanticPlan,
        *,
        normalized_plan: SemanticPlan | None = None,
        values: tuple[SemanticPlanValidationValue, ...] = (),
    ) -> SemanticPlanValidationResult:
        return cls(
            status=SemanticPlanValidationStatus.VALID,
            reason=SemanticPlanValidationReason.VALID,
            original_plan=plan,
            validated_plan=normalized_plan or plan,
            values=values,
        )

    @classmethod
    def clarify(
        cls,
        plan: SemanticPlan,
        reason: SemanticPlanValidationReason,
        *,
        values: tuple[SemanticPlanValidationValue, ...] = (),
    ) -> SemanticPlanValidationResult:
        return cls(
            status=SemanticPlanValidationStatus.CLARIFY,
            reason=reason,
            original_plan=plan,
            values=values,
        )

    @classmethod
    def reject(
        cls,
        reason: SemanticPlanValidationReason,
        *,
        plan: SemanticPlan | None = None,
        values: tuple[SemanticPlanValidationValue, ...] = (),
    ) -> SemanticPlanValidationResult:
        return cls(
            status=SemanticPlanValidationStatus.REJECT,
            reason=reason,
            original_plan=plan,
            values=values,
        )

    @classmethod
    def unavailable(
        cls,
        plan: SemanticPlan,
        reason: SemanticPlanValidationReason,
        *,
        values: tuple[SemanticPlanValidationValue, ...] = (),
    ) -> SemanticPlanValidationResult:
        return cls(
            status=SemanticPlanValidationStatus.UNAVAILABLE,
            reason=reason,
            original_plan=plan,
            values=values,
        )

    def to_trace_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "reason": self.reason.value,
            "can_execute": self.can_execute,
            "values": [value.to_trace_dict() for value in self.values],
        }


def _safe_trace_scalar(value: _TraceScalar) -> _TraceScalar:
    if isinstance(value, str):
        return redact_sensitive(" ".join(value.split()))[:MAX_VALIDATION_TRACE_TEXT]
    return value


def _validate_trace_scalar(value: _TraceScalar, name: str) -> None:
    if not isinstance(value, (str, int, float, bool, type(None))):
        raise TypeError(f"Validation {name} must be a trace-safe scalar.")
    if isinstance(value, str):
        if len(value) > MAX_VALIDATION_TRACE_TEXT:
            raise ValueError(f"Validation {name} exceeds trace text limit.")
        if value != redact_sensitive(value):
            raise ValueError(f"Validation {name} must be redacted before storage.")
        if any(ord(character) < 32 for character in value):
            raise ValueError(f"Validation {name} must not contain control characters.")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"Validation {name} must be a finite number.")


__all__ = [
    "MAX_VALIDATION_TRACE_TEXT",
    "SemanticPlanValidationReason",
    "SemanticPlanValidationResult",
    "SemanticPlanValidationStatus",
    "SemanticPlanValidationValue",
]
