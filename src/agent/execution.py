"""Execution contracts after authority and before canonical observation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Protocol, runtime_checkable

from src.agent.authority import (
    AuthorizationReason,
    AuthorizationResult,
    AuthorizationStatus,
)
from src.agent.capabilities import CapabilityDefinition
from src.agent.contracts import (
    AgentObservation,
    ObservationStatus,
)
from src.agent.permissions import EffectClass


@dataclass(frozen=True, slots=True)
class AuthorizedExecutionRequest:
    """Only data that survived the canonical authority boundary."""

    capability_id: str
    runtime_binding: str
    effect: EffectClass
    target_ref: str | None
    source_ref: str | None
    arguments: Mapping[str, object]

    def __post_init__(self) -> None:
        if not isinstance(self.capability_id, str) or not self.capability_id:
            raise ValueError("capability_id must be non-empty.")

        if not isinstance(self.runtime_binding, str) or not self.runtime_binding:
            raise ValueError("runtime_binding must be non-empty.")

        if not isinstance(self.effect, EffectClass):
            raise TypeError("effect must be EffectClass.")

        if not isinstance(self.arguments, Mapping):
            raise TypeError("arguments must be a mapping.")

        object.__setattr__(
            self,
            "arguments",
            MappingProxyType(dict(self.arguments)),
        )

    @classmethod
    def from_authorization(
        cls,
        capability: CapabilityDefinition,
        authorization: AuthorizationResult,
    ) -> AuthorizedExecutionRequest:
        if not isinstance(capability, CapabilityDefinition):
            raise TypeError(
                "capability must be CapabilityDefinition."
            )

        if not isinstance(authorization, AuthorizationResult):
            raise TypeError(
                "authorization must be AuthorizationResult."
            )

        if not authorization.valid:
            raise ValueError(
                "execution request requires valid authorization."
            )

        if capability.capability_id != authorization.capability_id:
            raise ValueError(
                "capability does not match authorization."
            )

        if capability.effect is not authorization.effect:
            raise ValueError(
                "capability effect does not match authorization."
            )

        return cls(
            capability_id=capability.capability_id,
            runtime_binding=capability.runtime_binding,
            effect=capability.effect,
            target_ref=authorization.target_ref,
            source_ref=authorization.source_ref,
            arguments=authorization.normalized_arguments,
        )


class ExecutionStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    BLOCKED = "blocked"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class AgentExecutionResult:
    status: ExecutionStatus
    dispatched: bool
    facts: tuple[Mapping[str, object], ...] = ()
    summary: str | None = None
    provenance: Mapping[str, object] = field(default_factory=dict)
    reason: str | None = None
    recoverable: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.status, ExecutionStatus):
            raise TypeError("status must be ExecutionStatus.")

        if type(self.dispatched) is not bool:
            raise TypeError("dispatched must be bool.")

        if (
            self.status is ExecutionStatus.SUCCESS
            and not self.dispatched
        ):
            raise ValueError(
                "successful execution must be dispatched."
            )

        if not isinstance(self.facts, tuple):
            raise TypeError("facts must be a tuple.")

        if any(not isinstance(item, Mapping) for item in self.facts):
            raise TypeError(
                "facts must contain mappings."
            )

        if self.summary is not None and (
            not isinstance(self.summary, str)
            or not self.summary
        ):
            raise ValueError(
                "summary must be non-empty text or None."
            )

        if self.reason is not None and (
            not isinstance(self.reason, str)
            or not self.reason
        ):
            raise ValueError(
                "reason must be non-empty text or None."
            )

        if not isinstance(self.provenance, Mapping):
            raise TypeError(
                "provenance must be a mapping."
            )

        if type(self.recoverable) is not bool:
            raise TypeError(
                "recoverable must be bool."
            )

        object.__setattr__(
            self,
            "provenance",
            MappingProxyType(dict(self.provenance)),
        )

    def to_observation(
        self,
        action_id: int,
        request: AuthorizedExecutionRequest,
    ) -> AgentObservation:
        if not isinstance(request, AuthorizedExecutionRequest):
            raise TypeError(
                "request must be AuthorizedExecutionRequest."
            )

        status = {
            ExecutionStatus.SUCCESS: ObservationStatus.SUCCESS,
            ExecutionStatus.ERROR: ObservationStatus.ERROR,
            ExecutionStatus.BLOCKED: ObservationStatus.BLOCKED,
            ExecutionStatus.UNAVAILABLE: ObservationStatus.UNAVAILABLE,
        }[self.status]

        return AgentObservation(
            action_id=action_id,
            capability_id=request.capability_id,
            status=status,
            facts=self.facts,
            summary=self.summary,
            target_ref=request.target_ref,
            source_ref=request.source_ref,
            provenance=self.provenance,
            reason=self.reason,
            recoverable=self.recoverable,
        )


@runtime_checkable
class AuthorizedActionExecutor(Protocol):
    def execute(
        self,
        request: AuthorizedExecutionRequest,
    ) -> AgentExecutionResult:
        """Execute at most one already-authorized capability."""


def authorization_observation(
    action_id: int,
    authorization: AuthorizationResult,
) -> AgentObservation:
    if not isinstance(authorization, AuthorizationResult):
        raise TypeError(
            "authorization must be AuthorizationResult."
        )

    if authorization.valid:
        raise ValueError(
            "valid authorization does not create a failure observation."
        )

    status = _authorization_status(authorization)
    recoverable = _authorization_recoverable(authorization)

    return AgentObservation(
        action_id=action_id,
        capability_id=authorization.capability_id,
        status=status,
        target_ref=authorization.target_ref,
        source_ref=authorization.source_ref,
        reason=authorization.reason.value,
        recoverable=recoverable,
    )


def _authorization_status(
    authorization: AuthorizationResult,
) -> ObservationStatus:
    if authorization.status is AuthorizationStatus.UNAVAILABLE:
        return ObservationStatus.UNAVAILABLE

    if authorization.status is AuthorizationStatus.APPROVAL_REQUIRED:
        return ObservationStatus.BLOCKED

    if authorization.reason in {
        AuthorizationReason.EFFECT_BLOCKED,
        AuthorizationReason.TARGET_NOT_ALLOWED,
        AuthorizationReason.SOURCE_NOT_ALLOWED,
    }:
        return ObservationStatus.BLOCKED

    return ObservationStatus.ERROR


def _authorization_recoverable(
    authorization: AuthorizationResult,
) -> bool:
    return authorization.reason not in {
        AuthorizationReason.EFFECT_BLOCKED,
        AuthorizationReason.APPROVAL_MISSING,
        AuthorizationReason.BUDGET_EXHAUSTED,
        AuthorizationReason.SAFETY_NOT_REVIEWED,
    }


__all__ = [
    "AgentExecutionResult",
    "AuthorizedActionExecutor",
    "AuthorizedExecutionRequest",
    "ExecutionStatus",
    "authorization_observation",
]
