"""Bounded Agent v2 observations built only from trusted typed results."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from src.agent.controller_contracts import (
    AgentObservation,
    AgentObservationStatus,
    _freeze_json_mapping,
    agent_observation_to_json,
)
from src.pipeline.agent_action_executor import (
    AgentActionExecutionReason,
    AgentActionExecutionResult,
    AgentActionExecutionStatus,
)
from src.pipeline.agent_action_validator import (
    AgentActionValidationReason,
    AgentActionValidationResult,
    AgentActionValidationStatus,
)
from src.pipeline.basic_calculator import (
    CalculatorContractResult,
    CalculatorResultStatus,
)
from src.pipeline.calculator_action_contract import CALCULATOR_CAPABILITY_ID
from src.pipeline.controller_capability_discovery import (
    CapabilityDiscoveryResult,
    CapabilityDiscoveryStatus,
)
from src.pipeline.evidence_package import EvidencePackage
from src.pipeline.fact import Fact, FactFreshness, FactValidity, thaw
from src.shared.execution.command_result import redact_sensitive
from src.tool.capability_result import CapabilityStatus
from src.tool.errors import CapabilityError

MAX_RETAINED_AGENT_OBSERVATIONS = 6
MAX_FACTS_PER_AGENT_OBSERVATION = 6
MAX_AGENT_OBSERVATION_BYTES = 1_024
MAX_AGENT_OBSERVATION_DETAIL_CHARS = 240
MAX_AGENT_OBSERVATION_WARNINGS = 3
MAX_AGENT_OBSERVATION_PROVENANCE_REFS = 6
MAX_AGENT_OBSERVATION_FACT_VALUE_BYTES = 256

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.-]{0,79}$")
_UNHEALTHY_STATUSES = frozenset(
    {
        AgentObservationStatus.BLOCKED,
        AgentObservationStatus.FAILED,
        AgentObservationStatus.PARTIAL,
        AgentObservationStatus.UNAVAILABLE,
        AgentObservationStatus.INVALID_ACTION,
    }
)
_FAILURE_FACT_VALIDITIES = frozenset(
    {
        FactValidity.COMMAND_FAILED,
        FactValidity.NOT_COLLECTED,
        FactValidity.UNSUPPORTED,
        FactValidity.SCHEMA_INVALID,
        FactValidity.STALE,
    }
)
_UNSAFE_FACT_VALUE = object()
_OPERATIONAL_FACT_VALUE_KEYS = frozenset(
    {
        "command",
        "cmd",
        "stdout",
        "stderr",
        "raw_data",
        "raw_payload",
        "payload",
        "response",
        "api_response",
        "body",
    }
)


@dataclass(frozen=True, slots=True)
class AgentObservationSerializer:
    """Convert v2 harness outputs to one compact controller observation."""

    def discovery(
        self,
        action_id: int,
        result: CapabilityDiscoveryResult,
        *,
        category: str | None = None,
    ) -> AgentObservation:
        if not isinstance(result, CapabilityDiscoveryResult):
            raise TypeError("result must be CapabilityDiscoveryResult.")
        category_id = _discovery_category(result.category or category)
        if result.status is CapabilityDiscoveryStatus.DISCOVERED:
            return self._fit(
                action_id=action_id,
                capability_id=f"discovery.{category_id}",
                status=AgentObservationStatus.SUCCESS,
                summary=(
                    f"discovered category={category_id} count={len(result.summaries)}"
                ),
                reason_code="discovered",
                recoverable=False,
            )
        if result.status is CapabilityDiscoveryStatus.UNKNOWN_CATEGORY:
            return self._fit(
                action_id=action_id,
                capability_id=f"discovery.{category_id}",
                status=AgentObservationStatus.INVALID_ACTION,
                reason_code="unknown_category",
                recoverable=True,
            )
        if result.status is CapabilityDiscoveryStatus.UNAVAILABLE_CATEGORY:
            return self._fit(
                action_id=action_id,
                capability_id=f"discovery.{category_id}",
                status=AgentObservationStatus.UNAVAILABLE,
                reason_code="unavailable_category",
                recoverable=True,
            )
        raise ValueError("Unknown capability discovery status.")

    def validation_failure(
        self,
        action_id: int,
        validation: AgentActionValidationResult,
    ) -> AgentObservation:
        if not isinstance(validation, AgentActionValidationResult):
            raise TypeError("validation must be AgentActionValidationResult.")
        if validation.status is AgentActionValidationStatus.VALID:
            raise ValueError("VALID validation results do not create observations.")
        status, recoverable = _validation_status(validation)
        return self._fit(
            action_id=action_id,
            capability_id=validation.capability_id,
            status=status,
            target_id=validation.target_id,
            source_id=validation.source_id,
            reason_code=validation.reason.value,
            recoverable=recoverable,
        )

    def execution(
        self,
        action_id: int,
        execution: AgentActionExecutionResult,
    ) -> AgentObservation:
        if not isinstance(execution, AgentActionExecutionResult):
            raise TypeError("execution must be AgentActionExecutionResult.")
        if execution.calculator_result is not None:
            return self.calculator(action_id, execution.calculator_result)
        if execution.status is AgentActionExecutionStatus.NOT_EXECUTED:
            return self._not_executed(action_id, execution)
        if execution.evidence is None:
            raise ValueError("Dispatched infrastructure execution requires evidence.")
        return self._evidence(
            action_id,
            execution.capability_id,
            execution.target_id,
            execution.source_id or execution.validation.source_id,
            execution.evidence,
        )

    def calculator(
        self,
        action_id: int,
        result: CalculatorContractResult,
    ) -> AgentObservation:
        if not isinstance(result, CalculatorContractResult):
            raise TypeError("result must be CalculatorContractResult.")
        status = {
            CalculatorResultStatus.SUCCESS: AgentObservationStatus.SUCCESS,
            CalculatorResultStatus.AMBIGUOUS: AgentObservationStatus.INVALID_ACTION,
            CalculatorResultStatus.INVALID: AgentObservationStatus.INVALID_ACTION,
            CalculatorResultStatus.UNSUPPORTED: AgentObservationStatus.UNAVAILABLE,
        }[result.status]
        return self._fit(
            action_id=action_id,
            capability_id=CALCULATOR_CAPABILITY_ID,
            status=status,
            facts=(result.to_dict(),),
            reason_code=None if result.ok else result.reason,
            recoverable=False,
        )

    def control_feedback(
        self,
        action_id: int,
        *,
        status: AgentObservationStatus,
        reason_code: str,
        safe_detail: str | None = None,
        capability_id: str = "harness.control",
        target_id: str | None = None,
        source_id: str | None = None,
        recoverable: bool = False,
    ) -> AgentObservation:
        """Serialize already-sanitized future harness feedback without policy."""

        if status not in _UNHEALTHY_STATUSES:
            raise ValueError(
                "control feedback must use a non-success observation status."
            )
        return self._fit(
            action_id=action_id,
            capability_id=capability_id,
            status=status,
            summary=_bounded_detail(safe_detail),
            target_id=target_id,
            source_id=source_id,
            reason_code=reason_code,
            recoverable=recoverable,
        )

    def _not_executed(
        self,
        action_id: int,
        execution: AgentActionExecutionResult,
    ) -> AgentObservation:
        mapping = {
            AgentActionExecutionReason.BUDGET_EXHAUSTED: (
                AgentObservationStatus.UNAVAILABLE,
                "budget_exhausted",
                False,
            ),
            AgentActionExecutionReason.CAPABILITY_BINDING_UNAVAILABLE: (
                AgentObservationStatus.UNAVAILABLE,
                "capability_binding_unavailable",
                True,
            ),
            AgentActionExecutionReason.VALIDATION_NOT_VALID: (
                AgentObservationStatus.INVALID_ACTION,
                "validation_not_valid",
                True,
            ),
        }
        try:
            status, reason_code, recoverable = mapping[execution.reason]
        except KeyError as exc:
            raise ValueError("Unknown non-executed action reason.") from exc
        return self._fit(
            action_id=action_id,
            capability_id=execution.capability_id,
            status=status,
            target_id=execution.target_id,
            source_id=execution.source_id or execution.validation.source_id,
            reason_code=reason_code,
            recoverable=recoverable,
        )

    def _evidence(
        self,
        action_id: int,
        capability_id: str,
        target_id: str | None,
        source_id: str | None,
        evidence: EvidencePackage,
    ) -> AgentObservation:
        status = _evidence_status(evidence)
        error = evidence.capability_error
        reason_code = None
        recoverable = False
        detail = None
        if status not in {
            AgentObservationStatus.SUCCESS,
            AgentObservationStatus.EMPTY_SUCCESS,
        }:
            reason_code, recoverable, detail = _capability_error_detail(
                error,
                evidence.capability_status,
                status,
            )
        facts = _compact_facts(evidence.facts)
        summary = _evidence_summary(status, evidence.warnings, detail)
        return self._fit(
            action_id=action_id,
            capability_id=capability_id,
            status=status,
            facts=facts,
            summary=summary,
            target_id=target_id,
            source_id=source_id,
            provenance_references=_provenance_references(facts),
            reason_code=reason_code,
            recoverable=recoverable,
        )

    @staticmethod
    def _fit(
        *,
        action_id: int,
        capability_id: str,
        status: AgentObservationStatus,
        facts: tuple[dict[str, object], ...] = (),
        summary: str | None = None,
        target_id: str | None = None,
        source_id: str | None = None,
        provenance_references: tuple[str, ...] = (),
        reason_code: str | None = None,
        recoverable: bool = False,
    ) -> AgentObservation:
        """Fit an observation by dropping whole facts before optional detail."""

        retained_facts = list(facts[:MAX_FACTS_PER_AGENT_OBSERVATION])
        retained_references = list(
            provenance_references[:MAX_AGENT_OBSERVATION_PROVENANCE_REFS]
        )
        candidate = _observation(
            action_id,
            capability_id,
            status,
            retained_facts,
            summary,
            target_id,
            source_id,
            retained_references,
            reason_code,
            recoverable,
        )
        while (
            _observation_bytes(candidate) > MAX_AGENT_OBSERVATION_BYTES
            and retained_facts
        ):
            _drop_lowest_priority_fact(retained_facts)
            retained_references = _references_for_compact_facts(
                retained_facts, retained_references
            )
            candidate = _observation(
                action_id,
                capability_id,
                status,
                retained_facts,
                summary,
                target_id,
                source_id,
                retained_references,
                reason_code,
                recoverable,
            )
        if _observation_bytes(candidate) > MAX_AGENT_OBSERVATION_BYTES and summary:
            candidate = _observation(
                action_id,
                capability_id,
                status,
                retained_facts,
                _core_summary(status),
                target_id,
                source_id,
                retained_references,
                reason_code,
                recoverable,
            )
        if (
            _observation_bytes(candidate) > MAX_AGENT_OBSERVATION_BYTES
            and candidate.summary is not None
            and status is not AgentObservationStatus.PARTIAL
        ):
            candidate = _observation(
                action_id,
                capability_id,
                status,
                retained_facts,
                None,
                target_id,
                source_id,
                retained_references,
                reason_code,
                recoverable,
            )
        if _observation_bytes(candidate) > MAX_AGENT_OBSERVATION_BYTES:
            raise ValueError(
                "Agent observation cannot fit without truncating identity."
            )
        return candidate


def serialize_discovery_observation(
    action_id: int,
    result: CapabilityDiscoveryResult,
    *,
    category: str | None = None,
) -> AgentObservation:
    return AgentObservationSerializer().discovery(action_id, result, category=category)


def serialize_validation_failure(
    action_id: int, validation: AgentActionValidationResult
) -> AgentObservation:
    return AgentObservationSerializer().validation_failure(action_id, validation)


def serialize_execution_observation(
    action_id: int, execution: AgentActionExecutionResult
) -> AgentObservation:
    return AgentObservationSerializer().execution(action_id, execution)


def serialize_calculator_observation(
    action_id: int, result: CalculatorContractResult
) -> AgentObservation:
    return AgentObservationSerializer().calculator(action_id, result)


def serialize_control_feedback(
    action_id: int,
    *,
    status: AgentObservationStatus,
    reason_code: str,
    safe_detail: str | None = None,
    capability_id: str = "harness.control",
    target_id: str | None = None,
    source_id: str | None = None,
    recoverable: bool = False,
) -> AgentObservation:
    return AgentObservationSerializer().control_feedback(
        action_id,
        status=status,
        reason_code=reason_code,
        safe_detail=safe_detail,
        capability_id=capability_id,
        target_id=target_id,
        source_id=source_id,
        recoverable=recoverable,
    )


def retain_agent_observations(
    observations: Iterable[AgentObservation],
    *,
    capability_id: str | None = None,
    target_id: str | None = None,
    source_id: str | None = None,
) -> tuple[AgentObservation, ...]:
    """Keep the newest and most useful fixed-size history for a future loop."""

    values = tuple(observations)
    if any(not isinstance(observation, AgentObservation) for observation in values):
        raise TypeError("observations must contain AgentObservation values.")
    if len(values) <= MAX_RETAINED_AGENT_OBSERVATIONS:
        return tuple(sorted(values, key=lambda item: item.action_id))
    newest_index = max(
        range(len(values)),
        key=lambda index: (values[index].action_id, index),
    )

    def priority(index: int) -> tuple[int, int, int, int]:
        observation = values[index]
        exact_match = _identity_matches(
            observation,
            capability_id=capability_id,
            target_id=target_id,
            source_id=source_id,
        )
        return (
            int(index != newest_index),
            int(observation.status not in _UNHEALTHY_STATUSES),
            int(not exact_match),
            -observation.action_id,
        )

    selected = sorted(range(len(values)), key=priority)[
        :MAX_RETAINED_AGENT_OBSERVATIONS
    ]
    return tuple(
        sorted((values[index] for index in selected), key=lambda item: item.action_id)
    )


def _validation_status(
    validation: AgentActionValidationResult,
) -> tuple[AgentObservationStatus, bool]:
    if validation.status is AgentActionValidationStatus.CLARIFY:
        return AgentObservationStatus.INVALID_ACTION, True
    if validation.status is AgentActionValidationStatus.UNAVAILABLE:
        return (
            AgentObservationStatus.UNAVAILABLE,
            validation.reason is not AgentActionValidationReason.BUDGET_EXHAUSTED,
        )
    if validation.status is not AgentActionValidationStatus.REJECT:
        raise ValueError("Unknown non-valid action validation status.")
    if validation.reason in {
        AgentActionValidationReason.SOURCE_FORBIDDEN,
        AgentActionValidationReason.CAPABILITY_MUTATING,
        AgentActionValidationReason.MUTATION_REQUESTED,
    }:
        return AgentObservationStatus.BLOCKED, False
    if validation.reason in {
        AgentActionValidationReason.ARGUMENT_UNSAFE,
        AgentActionValidationReason.URL_INVALID,
    }:
        return AgentObservationStatus.BLOCKED, True
    return AgentObservationStatus.INVALID_ACTION, True


def _evidence_status(evidence: EvidencePackage) -> AgentObservationStatus:
    status = {
        CapabilityStatus.VALID: AgentObservationStatus.SUCCESS,
        CapabilityStatus.VALID_EMPTY: AgentObservationStatus.EMPTY_SUCCESS,
        CapabilityStatus.PARTIAL: AgentObservationStatus.PARTIAL,
        CapabilityStatus.UNSUPPORTED: AgentObservationStatus.UNAVAILABLE,
        CapabilityStatus.INVALID_PARAMETERS: AgentObservationStatus.INVALID_ACTION,
        CapabilityStatus.COLLECTION_FAILED: AgentObservationStatus.FAILED,
        CapabilityStatus.PARSE_FAILED: AgentObservationStatus.FAILED,
    }[evidence.capability_status]
    if status in {
        AgentObservationStatus.SUCCESS,
        AgentObservationStatus.EMPTY_SUCCESS,
    } and any(not fact.usable for fact in evidence.facts):
        return AgentObservationStatus.PARTIAL
    return status


def _capability_error_detail(
    error: CapabilityError | None,
    fallback_status: CapabilityStatus,
    observation_status: AgentObservationStatus,
) -> tuple[str, bool, str | None]:
    if error is not None:
        return error.code.value, error.recoverable, _bounded_detail(error.message)
    if observation_status is AgentObservationStatus.PARTIAL and fallback_status in {
        CapabilityStatus.VALID,
        CapabilityStatus.VALID_EMPTY,
    }:
        return "partial_evidence", False, None
    return fallback_status.value, False, None


def _evidence_summary(
    status: AgentObservationStatus,
    warnings: tuple[str, ...],
    detail: str | None,
) -> str | None:
    core_summary = _core_summary(status)
    pieces: list[str] = [core_summary] if core_summary is not None else []
    for item in (detail, *_bounded_warnings(warnings)):
        if (
            item is not None
            and len("; ".join((*pieces, item))) <= MAX_AGENT_OBSERVATION_DETAIL_CHARS
        ):
            pieces.append(item)
    return "; ".join(pieces) or None


def _core_summary(status: AgentObservationStatus) -> str | None:
    return {
        AgentObservationStatus.PARTIAL: "partial evidence",
        AgentObservationStatus.EMPTY_SUCCESS: "empty success",
        AgentObservationStatus.UNAVAILABLE: "unavailable",
        AgentObservationStatus.INVALID_ACTION: "invalid action",
        AgentObservationStatus.BLOCKED: "blocked",
        AgentObservationStatus.FAILED: "failed",
    }.get(status)


def _compact_facts(facts: tuple[Fact, ...]) -> tuple[dict[str, object], ...]:
    ordered = sorted(
        enumerate(facts),
        key=lambda item: (_fact_priority(item[1]), item[0]),
    )
    return tuple(
        _compact_fact(fact) for _, fact in ordered[:MAX_FACTS_PER_AGENT_OBSERVATION]
    )


def _compact_fact(fact: Fact) -> dict[str, object]:
    value = _safe_fact_value(fact.value)
    if value is _UNSAFE_FACT_VALUE:
        value = {"value_omitted": "unsafe"}
    elif _serialized_bytes(value) > MAX_AGENT_OBSERVATION_FACT_VALUE_BYTES:
        value = {"value_omitted": "oversize"}
    compact: dict[str, object] = {
        "id": fact.id,
        "subject": fact.subject,
        "metric": fact.metric,
        "value": value,
        "observed_at": fact.observed_at.isoformat(),
        "validity": fact.validity.value,
        "freshness": fact.freshness.value,
        "source": fact.source,
        "target": fact.target,
        "confidence": fact.confidence,
        "provenance_id": fact.provenance.id,
    }
    if fact.unit:
        compact["unit"] = fact.unit
    reference = fact.provenance.source_reference
    if reference is not None and len(reference) <= MAX_AGENT_OBSERVATION_DETAIL_CHARS:
        compact["source_reference"] = reference
    provider = _safe_provider(fact.dimensions.get("provider"))
    if provider is not None:
        compact["provider"] = provider
    return compact


def _safe_provider(value: object) -> str | None:
    """Expose one credential-free external-provider label, never an endpoint."""

    if not isinstance(value, str):
        return None
    provider = redact_sensitive(value.strip())
    if (
        not provider
        or len(provider) > 80
        or any(token in provider.casefold() for token in ("://", "@", "?", "="))
    ):
        return None
    return provider


def _provenance_references(facts: tuple[dict[str, object], ...]) -> tuple[str, ...]:
    references: list[str] = []
    for fact in facts:
        provenance_id = fact.get("provenance_id")
        if isinstance(provenance_id, str) and provenance_id not in references:
            references.append(provenance_id)
        if len(references) == MAX_AGENT_OBSERVATION_PROVENANCE_REFS:
            break
    return tuple(references)


def _references_for_compact_facts(
    facts: list[dict[str, object]], references: list[str]
) -> list[str]:
    required = {
        value for fact in facts if isinstance((value := fact.get("provenance_id")), str)
    }
    return [reference for reference in references if reference in required]


def _drop_lowest_priority_fact(facts: list[dict[str, object]]) -> None:
    priorities = [_compact_fact_priority(fact) for fact in facts]
    lowest = max(priorities)
    index = max(
        index for index, priority in enumerate(priorities) if priority == lowest
    )
    facts.pop(index)


def _compact_fact_priority(fact: dict[str, object]) -> int:
    validity = fact.get("validity")
    freshness = fact.get("freshness")
    if validity == FactValidity.CONTRADICTORY.value:
        return 0
    if freshness == FactFreshness.STALE.value or validity in {
        item.value for item in _FAILURE_FACT_VALIDITIES
    }:
        return 1
    if validity == FactValidity.VALID_EMPTY.value:
        return 2
    return 3


def _fact_priority(fact: Fact) -> int:
    if fact.validity is FactValidity.CONTRADICTORY:
        return 0
    if (
        fact.freshness is FactFreshness.STALE
        or fact.validity in _FAILURE_FACT_VALIDITIES
    ):
        return 1
    if fact.validity is FactValidity.VALID_EMPTY:
        return 2
    return 3


def _bounded_warnings(warnings: tuple[str, ...]) -> tuple[str, ...]:
    bounded: list[str] = []
    for warning in warnings:
        safe = _bounded_detail(warning)
        if safe is not None:
            bounded.append(safe)
        if len(bounded) == MAX_AGENT_OBSERVATION_WARNINGS:
            break
    return tuple(bounded)


def _bounded_detail(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    safe = redact_sensitive(" ".join(value.split()))
    return safe if safe and len(safe) <= MAX_AGENT_OBSERVATION_DETAIL_CHARS else None


def _serialized_bytes(value: object) -> int:
    try:
        return len(
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        )
    except (TypeError, ValueError):
        return MAX_AGENT_OBSERVATION_FACT_VALUE_BYTES + 1


def _safe_fact_value(value: object) -> object:
    """Return an all-or-nothing safe Fact value for AgentObservation."""

    candidate = _redact_fact_value_item(thaw(value))
    if candidate is _UNSAFE_FACT_VALUE or _has_operational_value_key(candidate):
        return _UNSAFE_FACT_VALUE
    try:
        _freeze_json_mapping(
            {"value": candidate},
            "fact.value",
            max_items=1,
            forbid_action_keys=True,
        )
    except (TypeError, ValueError):
        return _UNSAFE_FACT_VALUE
    return candidate


def _redact_fact_value_item(value: object) -> object:
    if value is None or type(value) in {bool, int}:
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else _UNSAFE_FACT_VALUE
    if isinstance(value, str):
        safe = redact_sensitive(value)
        return safe if safe and safe == safe.strip() else _UNSAFE_FACT_VALUE
    if isinstance(value, Mapping):
        compact: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key or key != key.strip():
                return _UNSAFE_FACT_VALUE
            safe_item = _redact_fact_value_item(item)
            if safe_item is _UNSAFE_FACT_VALUE:
                return _UNSAFE_FACT_VALUE
            compact[key] = safe_item
        return compact
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        compact_items: list[object] = []
        for item in value:
            safe_item = _redact_fact_value_item(item)
            if safe_item is _UNSAFE_FACT_VALUE:
                return _UNSAFE_FACT_VALUE
            compact_items.append(safe_item)
        return compact_items
    return _UNSAFE_FACT_VALUE


def _has_operational_value_key(value: object) -> bool:
    if isinstance(value, Mapping):
        return any(
            _normalized_value_key(key) in _OPERATIONAL_FACT_VALUE_KEYS
            or _has_operational_value_key(item)
            for key, item in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_has_operational_value_key(item) for item in value)
    return False


def _normalized_value_key(key: object) -> str:
    return str(key).casefold().replace("-", "_").replace(" ", "_")


def _observation_bytes(observation: AgentObservation) -> int:
    return len(agent_observation_to_json(observation).encode("utf-8"))


def _observation(
    action_id: int,
    capability_id: str,
    status: AgentObservationStatus,
    facts: list[dict[str, object]],
    summary: str | None,
    target_id: str | None,
    source_id: str | None,
    provenance_references: list[str],
    reason_code: str | None,
    recoverable: bool,
) -> AgentObservation:
    return AgentObservation(
        action_id=action_id,
        capability_id=capability_id,
        status=status,
        facts=tuple(facts),
        summary=summary,
        target_id=target_id,
        source_id=source_id,
        provenance_references=tuple(provenance_references),
        reason_code=reason_code,
        recoverable=recoverable,
    )


def _discovery_category(category: str | None) -> str:
    if isinstance(category, str) and _IDENTIFIER.fullmatch(category):
        return category
    return "unknown"


def _identity_matches(
    observation: AgentObservation,
    *,
    capability_id: str | None,
    target_id: str | None,
    source_id: str | None,
) -> bool:
    return (
        (capability_id is None or observation.capability_id == capability_id)
        and (target_id is None or observation.target_id == target_id)
        and (source_id is None or observation.source_id == source_id)
    )


__all__ = [
    "MAX_AGENT_OBSERVATION_BYTES",
    "MAX_AGENT_OBSERVATION_DETAIL_CHARS",
    "MAX_AGENT_OBSERVATION_FACT_VALUE_BYTES",
    "MAX_AGENT_OBSERVATION_PROVENANCE_REFS",
    "MAX_AGENT_OBSERVATION_WARNINGS",
    "MAX_FACTS_PER_AGENT_OBSERVATION",
    "MAX_RETAINED_AGENT_OBSERVATIONS",
    "AgentObservationSerializer",
    "retain_agent_observations",
    "serialize_calculator_observation",
    "serialize_control_feedback",
    "serialize_discovery_observation",
    "serialize_execution_observation",
    "serialize_validation_failure",
]
