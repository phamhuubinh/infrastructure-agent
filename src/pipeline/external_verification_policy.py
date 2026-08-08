"""Pure policy for deterministic external-verification routing.

The policy is deliberately ignorant of providers, credentials, and network
state.  It says whether a request *requires* external evidence; a later
planner decides whether that evidence can be collected under the configured
budget and source constraints.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from src.pipeline.request_frame import RequestFrame
from src.pipeline.request_semantics import ExternalNeed, SourceConstraint


class ExternalVerificationDecision(Enum):
    NONE = auto()
    REQUIRED = auto()
    EXPLICIT = auto()
    URL = auto()


@dataclass(frozen=True, slots=True)
class ExternalVerificationPolicyResult:
    decision: ExternalVerificationDecision
    reason: str
    blocked_by_source_constraint: bool = False

    @property
    def requires_verification(self) -> bool:
        return self.decision is not ExternalVerificationDecision.NONE


class ExternalVerificationPolicy:
    """Map RequestFrame semantics to a provider-independent decision."""

    def decide(self, frame: RequestFrame) -> ExternalVerificationPolicyResult:
        if frame.external_need is ExternalNeed.NONE:
            return ExternalVerificationPolicyResult(
                ExternalVerificationDecision.NONE,
                "stable knowledge or live-environment request",
            )

        if SourceConstraint.NO_INTERNET in frame.source_constraints or SourceConstraint.INTERNET in frame.excluded_sources:
            return ExternalVerificationPolicyResult(
                self._decision(frame.external_need),
                "external verification conflicts with the no-Internet source constraint",
                blocked_by_source_constraint=True,
            )

        if frame.url_error:
            return ExternalVerificationPolicyResult(
                ExternalVerificationDecision.URL,
                frame.url_error,
            )

        return ExternalVerificationPolicyResult(
            self._decision(frame.external_need),
            {
                ExternalNeed.REQUIRED: "currentness requires external evidence",
                ExternalNeed.EXPLICIT: "user explicitly requested external verification",
                ExternalNeed.URL: "user supplied an explicit URL",
            }[frame.external_need],
        )

    @staticmethod
    def _decision(need: ExternalNeed) -> ExternalVerificationDecision:
        return {
            ExternalNeed.REQUIRED: ExternalVerificationDecision.REQUIRED,
            ExternalNeed.EXPLICIT: ExternalVerificationDecision.EXPLICIT,
            ExternalNeed.URL: ExternalVerificationDecision.URL,
        }[need]
