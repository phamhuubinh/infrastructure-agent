"""Deterministic completion checks for the bounded Agent v2 controller."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Final

from src.agent.controller_contracts import (
    AgentObservation,
    AgentObservationStatus,
    AgentRunState,
)
from src.agent.final_response_guard import (
    FinalResponseConstraints,
    FinalResponseGuard,
    FinalResponseViolation,
    response_is_honestly_unavailable_or_unverified,
)
from src.model.action_receipt import guard_action_claims
from src.pipeline.basic_calculator import (
    CalculatorContractResult,
    CalculatorOperation,
    CalculatorResultStatus,
)
from src.pipeline.calculator_action_contract import CALCULATOR_CAPABILITY_ID
from src.pipeline.hard_request_constraints import HardRequestConstraints


class CompletionCheckStatus(str, Enum):
    PASSED = "passed"
    REJECTED = "rejected"


class CompletionCheckReason(str, Enum):
    REFUSAL_REQUIRED = "goal_unresolved.refusal_required"
    CURRENT_EVIDENCE_MISSING = "goal_unresolved.current_evidence_missing"
    TARGET_MISMATCH = "goal_unresolved.target_mismatch"
    SOURCE_REQUIREMENT_UNSATISFIED = "goal_unresolved.source_requirement_unsatisfied"
    URL_REQUIREMENT_UNSATISFIED = "goal_unresolved.url_requirement_unsatisfied"
    CALCULATOR_CONFLICT = "goal_unresolved.calculator_conflict"
    CALCULATOR_EVIDENCE_INVALID = "goal_unresolved.calculator_evidence_invalid"
    CLAIM_NOT_OBSERVED = "goal_unresolved.claim_not_observed"
    EVIDENCE_INSUFFICIENT = "goal_unresolved.evidence_insufficient"


@dataclass(frozen=True, slots=True)
class CompletionCheckResult:
    status: CompletionCheckStatus
    reason: CompletionCheckReason | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, CompletionCheckStatus):
            raise TypeError("status must be a CompletionCheckStatus.")
        if self.status is CompletionCheckStatus.PASSED and self.reason is not None:
            raise ValueError("Passed completion checks may not include a reason.")
        if self.status is CompletionCheckStatus.REJECTED and self.reason is None:
            raise ValueError("Rejected completion checks require a reason.")

    @property
    def passed(self) -> bool:
        return self.status is CompletionCheckStatus.PASSED


_USABLE_VALIDITIES: Final = frozenset({"valid", "valid_empty"})
_SUCCESS_STATUSES: Final = frozenset(
    {AgentObservationStatus.SUCCESS, AgentObservationStatus.EMPTY_SUCCESS}
)
_EXECUTION_CLAIM: Final = re.compile(
    r"\b(?:the\s+)?(?:tool|command|capability)\s+"
    r"(?:was\s+)?(?:executed|ran|run|completed|succeeded|successful)\b"
    r"|\b(?:i|orion)\s+(?:executed|ran|completed)\s+"
    r"(?:the\s+)?(?:tool|command|capability)\b",
    re.IGNORECASE,
)
_INVALID_CALCULATOR_EVIDENCE = object()


class CompletionCheck:
    """Check only hard v2 completion invariants over compact observations."""

    def __init__(self, final_response_guard: FinalResponseGuard | None = None) -> None:
        if final_response_guard is not None and not isinstance(
            final_response_guard, FinalResponseGuard
        ):
            raise TypeError("final_response_guard must be FinalResponseGuard or None.")
        self._final_response_guard = final_response_guard or FinalResponseGuard()

    def check(
        self,
        *,
        raw_request: str,
        hard_constraints: HardRequestConstraints,
        run_state: AgentRunState,
        final_candidate: str,
    ) -> CompletionCheckResult:
        if not isinstance(raw_request, str) or not raw_request.strip():
            raise ValueError("raw_request must be non-empty text.")
        if not isinstance(hard_constraints, HardRequestConstraints):
            raise TypeError("hard_constraints must be HardRequestConstraints.")
        if not isinstance(run_state, AgentRunState):
            raise TypeError("run_state must be AgentRunState.")
        if raw_request != run_state.raw_request:
            raise ValueError("raw_request must equal run_state.raw_request.")
        if not isinstance(final_candidate, str) or not final_candidate.strip():
            raise ValueError("final_candidate must be non-empty text.")

        unavailable = response_is_honestly_unavailable_or_unverified(final_candidate)
        observations = run_state.observations
        guarded_action_claim = guard_action_claims(final_candidate, ())

        if hard_constraints.sensitive_refusal_reason is not None:
            return _rejected(CompletionCheckReason.REFUSAL_REQUIRED)
        if guarded_action_claim != final_candidate:
            if hard_constraints.mutation_requested:
                return _rejected(CompletionCheckReason.REFUSAL_REQUIRED)
            return _rejected(CompletionCheckReason.CLAIM_NOT_OBSERVED)

        if hard_constraints.explicit_target is not None:
            expected_target = (
                hard_constraints.explicit_target.registered_target
                or hard_constraints.explicit_target.value
            )
            if not _has_matching_identity(observations, "target", expected_target):
                if not unavailable:
                    return _rejected(CompletionCheckReason.TARGET_MISMATCH)

        excluded_sources = {
            source.name.casefold() for source in hard_constraints.excluded_sources
        }
        for source in hard_constraints.source_constraints:
            if (
                not _has_matching_source(
                    observations, source.name.casefold(), excluded_sources
                )
                and not unavailable
            ):
                return _rejected(CompletionCheckReason.SOURCE_REQUIREMENT_UNSATISFIED)

        if hard_constraints.explicit_url is not None and not _has_matching_url(
            observations, hard_constraints.explicit_url
        ):
            if not unavailable:
                return _rejected(CompletionCheckReason.URL_REQUIREMENT_UNSATISFIED)

        if hard_constraints.requires_fresh_evidence and not _has_fresh_fact(
            observations
        ):
            if not unavailable:
                return _rejected(CompletionCheckReason.CURRENT_EVIDENCE_MISSING)

        calculator = _latest_calculator_result(observations)
        if calculator is _INVALID_CALCULATOR_EVIDENCE:
            return _rejected(CompletionCheckReason.CALCULATOR_EVIDENCE_INVALID)
        if isinstance(calculator, CalculatorContractResult):
            guarded = self._final_response_guard.validate(
                final_candidate,
                FinalResponseConstraints(calculator_result=calculator),
            )
            if FinalResponseViolation.CALCULATOR_MISMATCH in guarded.violations:
                return _rejected(CompletionCheckReason.CALCULATOR_CONFLICT)

        if _EXECUTION_CLAIM.search(final_candidate) and not _has_successful_execution(
            observations
        ):
            return _rejected(CompletionCheckReason.CLAIM_NOT_OBSERVED)

        if _only_unsuccessful_execution_evidence(observations) and not unavailable:
            return _rejected(CompletionCheckReason.EVIDENCE_INSUFFICIENT)

        return CompletionCheckResult(CompletionCheckStatus.PASSED)


def _rejected(reason: CompletionCheckReason) -> CompletionCheckResult:
    return CompletionCheckResult(CompletionCheckStatus.REJECTED, reason)


def _successful(observation: AgentObservation) -> bool:
    return observation.status in _SUCCESS_STATUSES


def _usable_fact(fact: object) -> bool:
    return (
        isinstance(fact, Mapping)
        and fact.get("validity") in _USABLE_VALIDITIES
        and fact.get("freshness") != "stale"
    )


def _has_matching_identity(
    observations: tuple[AgentObservation, ...], identity: str, expected: str
) -> bool:
    expected_value = expected.casefold()
    for observation in observations:
        if not _successful(observation):
            continue
        observation_value = (
            observation.target_id if identity == "target" else observation.source_id
        )
        if (
            isinstance(observation_value, str)
            and observation_value.casefold() == expected_value
        ):
            return True
        if any(
            _usable_fact(fact)
            and isinstance(fact.get(identity), str)
            and fact[identity].casefold() == expected_value
            for fact in observation.facts
        ):
            return True
    return False


def _has_matching_source(
    observations: tuple[AgentObservation, ...], expected: str, excluded: set[str]
) -> bool:
    if expected in excluded:
        return False
    for observation in observations:
        if not _successful(observation):
            continue
        identities = [observation.source_id]
        identities.extend(
            fact.get("source") for fact in observation.facts if _usable_fact(fact)
        )
        if any(
            isinstance(identity, str)
            and identity.casefold() == expected
            and identity.casefold() not in excluded
            for identity in identities
        ):
            return True
    return False


def _has_matching_url(
    observations: tuple[AgentObservation, ...], expected: str
) -> bool:
    return any(
        _successful(observation)
        and any(
            _usable_fact(fact) and fact.get("source_reference") == expected
            for fact in observation.facts
        )
        for observation in observations
    )


def _has_fresh_fact(observations: tuple[AgentObservation, ...]) -> bool:
    return any(
        _successful(observation)
        and any(
            _usable_fact(fact) and fact.get("freshness") == "fresh"
            for fact in observation.facts
        )
        for observation in observations
    )


def _latest_calculator_result(
    observations: tuple[AgentObservation, ...],
) -> CalculatorContractResult | object | None:
    candidates = sorted(
        (
            observation
            for observation in observations
            if observation.capability_id == CALCULATOR_CAPABILITY_ID
            and observation.status is AgentObservationStatus.SUCCESS
        ),
        key=lambda observation: observation.action_id,
        reverse=True,
    )
    if not candidates:
        return None
    facts = candidates[0].facts
    if len(facts) != 1:
        return _INVALID_CALCULATOR_EVIDENCE
    fact = facts[0]
    try:
        status = CalculatorResultStatus(fact["status"])
        operation_value = fact["operation"]
        operation = (
            None if operation_value is None else CalculatorOperation(operation_value)
        )
        value_value = fact["value"]
        value = None if value_value is None else Decimal(value_value)
        if value is not None and not value.is_finite():
            raise InvalidOperation
        unit = fact["unit"]
        reason = fact["reason"]
        if not isinstance(unit, (str, type(None))) or not isinstance(
            reason, (str, type(None))
        ):
            raise TypeError
        if (
            status is not CalculatorResultStatus.SUCCESS
            or operation is None
            or value is None
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return _INVALID_CALCULATOR_EVIDENCE
    return CalculatorContractResult(status, operation, value, unit, reason)


def _has_successful_execution(observations: tuple[AgentObservation, ...]) -> bool:
    return any(
        _successful(observation)
        and not observation.capability_id.startswith("discovery.")
        and observation.capability_id != "harness.control"
        for observation in observations
    )


def _only_unsuccessful_execution_evidence(
    observations: tuple[AgentObservation, ...],
) -> bool:
    evidence = tuple(
        observation
        for observation in observations
        if not observation.capability_id.startswith("discovery.")
        and observation.capability_id != "harness.control"
    )
    return bool(evidence) and not any(
        _successful(observation) for observation in evidence
    )


__all__ = [
    "CompletionCheck",
    "CompletionCheckReason",
    "CompletionCheckResult",
    "CompletionCheckStatus",
]
