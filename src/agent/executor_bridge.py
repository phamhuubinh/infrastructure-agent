"""Canonical executor bridge for already-authorized Orion actions.

This module owns runtime binding only. It never interprets user prose, selects
capabilities, resolves aliases, changes permission policy, or invents fallback
targets/sources.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

from src.agent.execution import (
    AgentExecutionResult,
    AuthorizedExecutionRequest,
    ExecutionStatus,
)
from src.agent.permissions import EffectClass
from src.pipeline.basic_calculator import (
    CalculatorResultStatus,
    calculate_request,
)
from src.pipeline.calculator_action_contract import (
    CALCULATOR_CAPABILITY_ID,
    CalculatorActionBindingError,
    bind_calculator_action,
)
from src.pipeline.evidence_merge import EvidenceMerge
from src.pipeline.evidence_package import EvidencePackage
from src.pipeline.external_verification import (
    ExternalVerificationExecutor,
)
from src.pipeline.fact import Fact, thaw
from src.pipeline.internet_action_contract import (
    INTERNET_CURRENT_CAPABILITY_ID,
    INTERNET_FETCH_URL_CAPABILITY_ID,
    InternetActionBindingError,
    InternetActionKind,
    bind_internet_action,
)
from src.shared.redaction import redact_sensitive
from src.tool.capability_result import CapabilityStatus
from src.tool.knowledge_tool import KnowledgeTool

_MAX_FACTS = 8
_MAX_COLLECTION_ITEMS = 16
_MAX_VALUE_DEPTH = 6
_MAX_STRING_CHARS = 1_024

_FORBIDDEN_OUTPUT_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "bearer",
        "body",
        "cmd",
        "command",
        "cookie",
        "credential",
        "credentials",
        "password",
        "private_key",
        "proxy_authorization",
        "raw_data",
        "raw_payload",
        "response",
        "secret",
        "set_cookie",
        "shell",
        "stderr",
        "stdout",
        "token",
    }
)

_DROP = object()


@dataclass(frozen=True, slots=True)
class _KnowledgeRoute:
    source: str
    resource: str
    source_kind: str
    effect: EffectClass


class CanonicalActionExecutor:
    """Dispatch one already-authorized canonical action."""

    def __init__(
        self,
        knowledge_tool: KnowledgeTool,
        *,
        external_verification: ExternalVerificationExecutor | None = None,
    ) -> None:
        if not isinstance(knowledge_tool, KnowledgeTool):
            raise TypeError(
                "knowledge_tool must be KnowledgeTool."
            )

        self._knowledge_tool = knowledge_tool
        self._evidence_merge = EvidenceMerge()
        self._external_verification = (
            external_verification
            if external_verification is not None
            else ExternalVerificationExecutor(
                knowledge_tool
            )
        )

    def execute(
        self,
        request: AuthorizedExecutionRequest,
    ) -> AgentExecutionResult:
        if not isinstance(
            request,
            AuthorizedExecutionRequest,
        ):
            raise TypeError(
                "request must be AuthorizedExecutionRequest."
            )

        if request.runtime_binding == "knowledge.dispatch":
            return self._execute_knowledge(request)

        if request.runtime_binding == "calculator.execute":
            return self._execute_calculator(request)

        if request.runtime_binding == "internet.current":
            return self._execute_internet(
                request,
                expected_capability=(
                    INTERNET_CURRENT_CAPABILITY_ID
                ),
            )

        if request.runtime_binding == "internet.fetch_url":
            return self._execute_internet(
                request,
                expected_capability=(
                    INTERNET_FETCH_URL_CAPABILITY_ID
                ),
            )

        return AgentExecutionResult(
            status=ExecutionStatus.UNAVAILABLE,
            dispatched=False,
            reason="runtime_binding_unavailable",
            recoverable=True,
        )

    def _execute_knowledge(
        self,
        request: AuthorizedExecutionRequest,
    ) -> AgentExecutionResult:
        route = self._knowledge_route(request)

        if route is None:
            return AgentExecutionResult(
                status=ExecutionStatus.UNAVAILABLE,
                dispatched=False,
                reason="capability_binding_unavailable",
                recoverable=True,
            )

        # Registry metadata is checked again immediately before dispatch.
        # This catches capability/effect drift after the authority catalog
        # snapshot was constructed.
        if route.effect is not request.effect:
            return AgentExecutionResult(
                status=ExecutionStatus.BLOCKED,
                dispatched=False,
                summary=(
                    "Execution metadata no longer matches "
                    "the authorized effect."
                ),
                reason="effect_metadata_mismatch",
                recoverable=False,
            )

        arguments = {
            "source": route.source,
            "resource": route.resource,
            **dict(request.arguments),
        }

        try:
            result = self._knowledge_tool.execute(
                arguments
            )
        except Exception:
            # Once the runtime binding has been invoked, dispatch may
            # already have reached the underlying system. Conservatively
            # consume budget even when the bridge receives an exception.
            return AgentExecutionResult(
                status=ExecutionStatus.ERROR,
                dispatched=True,
                summary="Capability dispatch failed.",
                reason="dispatch_failure",
                recoverable=True,
            )

        if (
            result.security_inspected
            and not result.security_allowed
        ):
            return AgentExecutionResult(
                status=ExecutionStatus.BLOCKED,
                dispatched=True,
                summary=(
                    "Execution was blocked by runtime "
                    "security controls."
                ),
                reason="security_blocked",
                recoverable=False,
            )

        try:
            evidence = self._evidence_merge.package_from_result(
                capability_name=request.capability_id,
                evidence_name=request.capability_id,
                result=result,
                target=(
                    request.target_ref
                    or request.source_ref
                    or route.source
                ),
            )

            return evidence_execution_result(
                evidence,
                dispatched=True,
            )
        except Exception:
            return AgentExecutionResult(
                status=ExecutionStatus.ERROR,
                dispatched=True,
                summary="Capability evidence normalization failed.",
                reason="evidence_normalization_failure",
                recoverable=True,
            )

    def _execute_calculator(
        self,
        request: AuthorizedExecutionRequest,
    ) -> AgentExecutionResult:
        if (
            request.capability_id
            != CALCULATOR_CAPABILITY_ID
            or request.effect is not EffectClass.READ
            or request.target_ref is not None
            or request.source_ref is not None
        ):
            return AgentExecutionResult(
                status=ExecutionStatus.BLOCKED,
                dispatched=False,
                reason="calculator_binding_mismatch",
                recoverable=False,
            )

        try:
            calculator_request = bind_calculator_action(
                request.arguments
            )
        except CalculatorActionBindingError:
            return AgentExecutionResult(
                status=ExecutionStatus.ERROR,
                dispatched=False,
                reason="invalid_calculator_transport",
                recoverable=True,
            )

        try:
            result = calculate_request(calculator_request)
            fact = _sanitize_mapping(result.to_dict())
        except Exception:
            return AgentExecutionResult(
                status=ExecutionStatus.ERROR,
                dispatched=True,
                summary="Calculation execution failed.",
                reason="calculator_execution_failure",
                recoverable=True,
            )

        if result.status is CalculatorResultStatus.SUCCESS:
            return AgentExecutionResult(
                status=ExecutionStatus.SUCCESS,
                dispatched=True,
                facts=(fact,),
                summary="Calculation completed.",
                provenance={
                    "source": "deterministic",
                    "runtime_binding": "calculator.execute",
                },
            )

        return AgentExecutionResult(
            status=ExecutionStatus.ERROR,
            dispatched=True,
            facts=(fact,),
            summary="Calculation could not be completed.",
            reason=(
                result.reason
                or result.status.value
            ),
            recoverable=(
                result.status
                in {
                    CalculatorResultStatus.AMBIGUOUS,
                    CalculatorResultStatus.INVALID,
                }
            ),
            provenance={
                "source": "deterministic",
                "runtime_binding": "calculator.execute",
            },
        )

    def _execute_internet(
        self,
        request: AuthorizedExecutionRequest,
        *,
        expected_capability: str,
    ) -> AgentExecutionResult:
        if (
            request.capability_id != expected_capability
            or request.effect is not EffectClass.READ
            or request.target_ref is not None
            or request.source_ref is None
        ):
            return AgentExecutionResult(
                status=ExecutionStatus.BLOCKED,
                dispatched=False,
                reason="internet_binding_mismatch",
                recoverable=False,
            )

        try:
            if (
                self._knowledge_tool.source_kind(
                    request.source_ref
                )
                != "internet"
            ):
                return AgentExecutionResult(
                    status=ExecutionStatus.BLOCKED,
                    dispatched=False,
                    reason="internet_source_mismatch",
                    recoverable=False,
                )
        except KeyError:
            return AgentExecutionResult(
                status=ExecutionStatus.UNAVAILABLE,
                dispatched=False,
                reason="internet_source_unavailable",
                recoverable=True,
            )

        try:
            bound = bind_internet_action(
                request.capability_id,
                dict(request.arguments),
            )
        except InternetActionBindingError:
            return AgentExecutionResult(
                status=ExecutionStatus.ERROR,
                dispatched=False,
                reason="invalid_internet_transport",
                recoverable=True,
            )

        try:
            if bound.kind is InternetActionKind.CURRENT:
                outcome = (
                    self._external_verification
                    .collect_search_action(
                        source_id=request.source_ref,
                        queries=bound.queries,
                        max_results=5,
                        # Freshness belongs to the reviewed
                        # internet.current capability itself.
                        freshness_required=True,
                    )
                )
            else:
                outcome = (
                    self._external_verification
                    .collect_fetch_action(
                        source_id=request.source_ref,
                        url=bound.url or "",
                        # Existing extractor needs relevance text.
                        # The authorized URL is sufficient here;
                        # it does not grant additional authority.
                        user_request=bound.url or "",
                        freshness_required=False,
                    )
                )

            evidence = ExternalVerificationExecutor.action_evidence(
                outcome
            )
        except Exception:
            # Calling the external executor crosses the dispatch boundary.
            # A provider/network exception may happen after I/O occurred.
            return AgentExecutionResult(
                status=ExecutionStatus.ERROR,
                dispatched=True,
                summary="Internet execution failed.",
                reason="internet_dispatch_failure",
                recoverable=True,
            )

        dispatched = bool(
            outcome.search_calls
            or outcome.fetch_calls
        )

        result = evidence_execution_result(
            evidence,
            dispatched=dispatched,
        )

        usage = {
            "search_calls": outcome.search_calls,
            "fetch_calls": outcome.fetch_calls,
            "cache_hits": outcome.cache_hits,
            "total_bytes": outcome.total_bytes,
        }

        return AgentExecutionResult(
            status=result.status,
            dispatched=result.dispatched,
            facts=result.facts,
            summary=result.summary,
            provenance={
                **dict(result.provenance),
                "internet_usage": usage,
            },
            reason=result.reason,
            recoverable=result.recoverable,
        )

    def _knowledge_route(
        self,
        request: AuthorizedExecutionRequest,
    ) -> _KnowledgeRoute | None:
        category, separator, resource = (
            request.capability_id.partition(".")
        )

        if not separator or not resource:
            return None

        expected_kind = (
            "linux"
            if category == "host"
            else category
        )

        source = (
            request.target_ref
            if category == "host"
            else request.source_ref
        )

        if not isinstance(source, str) or not source:
            return None

        try:
            actual_kind = (
                self._knowledge_tool.source_kind(source)
            )
        except KeyError:
            return None

        if actual_kind != expected_kind:
            return None

        metadata = (
            self._knowledge_tool
            .get_capability_metadata()
        )
        entries = metadata.get(source)

        if not isinstance(entries, list):
            return None

        matching = [
            entry
            for entry in entries
            if (
                isinstance(entry, Mapping)
                and entry.get("name") == resource
            )
        ]

        if not matching:
            return None

        risks = {
            entry.get("mutation_risk")
            for entry in matching
        }

        if len(risks) != 1:
            return None

        risk = next(iter(risks))

        if risk == "none":
            effect = EffectClass.READ
        elif risk in {"low", "medium", "high"}:
            effect = EffectClass.WRITE
        else:
            return None

        return _KnowledgeRoute(
            source=source,
            resource=resource,
            source_kind=actual_kind,
            effect=effect,
        )


def evidence_execution_result(
    evidence: EvidencePackage,
    *,
    dispatched: bool,
) -> AgentExecutionResult:
    """Normalize trusted EvidencePackage into bounded model evidence."""

    if not isinstance(evidence, EvidencePackage):
        raise TypeError(
            "evidence must be EvidencePackage."
        )

    status = evidence.capability_status
    facts = tuple(
        projected
        for fact in evidence.facts[:_MAX_FACTS]
        if (projected := _project_fact(fact))
        is not None
    )

    provenance = {
        "capability_status": status.value,
        "source_tool": _safe_text(
            evidence.source_tool
        ),
        "source": _safe_text(evidence.source),
        "resource": _safe_text(evidence.resource),
        "schema_version": _safe_text(
            evidence.schema_version
        ),
        "stale": bool(evidence.stale),
        "fact_count": len(evidence.facts),
    }

    if status in {
        CapabilityStatus.VALID,
        CapabilityStatus.VALID_EMPTY,
    }:
        return AgentExecutionResult(
            status=ExecutionStatus.SUCCESS,
            dispatched=dispatched,
            facts=facts,
            summary=_success_summary(evidence),
            provenance=provenance,
        )

    if status is CapabilityStatus.PARTIAL:
        return AgentExecutionResult(
            status=ExecutionStatus.SUCCESS,
            dispatched=dispatched,
            facts=facts,
            summary="Partial evidence was collected.",
            provenance=provenance,
            reason="partial_evidence",
            recoverable=True,
        )

    if status is CapabilityStatus.UNSUPPORTED:
        return AgentExecutionResult(
            status=ExecutionStatus.UNAVAILABLE,
            dispatched=dispatched,
            facts=facts,
            summary="Capability is unavailable for this environment.",
            provenance=provenance,
            reason=status.value,
            recoverable=True,
        )

    return AgentExecutionResult(
        status=ExecutionStatus.ERROR,
        dispatched=dispatched,
        facts=facts,
        summary=_failure_summary(evidence),
        provenance=provenance,
        reason=status.value,
        recoverable=True,
    )


def _success_summary(
    evidence: EvidencePackage,
) -> str:
    if (
        evidence.capability_status
        is CapabilityStatus.VALID_EMPTY
    ):
        base = "Capability completed with no observations."
    else:
        base = "Capability completed."

    warnings: list[str] = []
    for warning in evidence.warnings[:2]:
        if isinstance(warning, str) and warning:
            safe_warning = _safe_text(warning)
            if safe_warning is not None:
                warnings.append(safe_warning)

    if warnings:
        base += " " + " ".join(warnings)

    return base[:2_000]


def _failure_summary(
    evidence: EvidencePackage,
) -> str:
    error = _safe_text(evidence.error)

    if error:
        return (
            "Capability execution failed: "
            + error
        )[:2_000]

    return "Capability execution failed."


def _project_fact(
    fact: Fact,
) -> dict[str, object] | None:
    if not isinstance(fact, Fact):
        return None

    safe_value = _safe_json(
        thaw(fact.value),
        depth=0,
    )

    if safe_value is _DROP:
        safe_value = None

    reference = _safe_text(
        fact.provenance.source_reference
    )

    result: dict[str, object] = {
        "id": fact.id,
        "subject": fact.subject,
        "metric": fact.metric,
        "value": safe_value,
        "unit": fact.unit,
        "observed_at": fact.observed_at.isoformat(),
        "source": fact.source,
        "target": fact.target,
        "validity": fact.validity.value,
        "freshness": fact.freshness.value,
        "confidence": fact.confidence,
    }

    if reference is not None:
        result["source_reference"] = reference

    safe_dimensions = _safe_json(
        thaw(fact.dimensions),
        depth=0,
    )

    if (
        safe_dimensions is not _DROP
        and safe_dimensions not in ({}, [])
    ):
        result["dimensions"] = safe_dimensions

    return result


def _sanitize_mapping(
    value: Mapping[str, object],
) -> dict[str, object]:
    safe = _safe_json(
        value,
        depth=0,
    )

    return (
        safe
        if isinstance(safe, dict)
        else {}
    )


def _safe_json(
    value: object,
    *,
    depth: int,
) -> object:
    if depth > _MAX_VALUE_DEPTH:
        return "<truncated>"

    if value is None or isinstance(
        value,
        (bool, int),
    ):
        return value

    if isinstance(value, float):
        return (
            value
            if math.isfinite(value)
            else "<non-finite>"
        )

    if isinstance(value, str):
        return redact_sensitive(value)[
            :_MAX_STRING_CHARS
        ]

    if isinstance(value, bytes):
        return redact_sensitive(
            value.decode(
                "utf-8",
                errors="replace",
            )
        )[:_MAX_STRING_CHARS]

    if isinstance(value, Enum):
        return _safe_json(
            value.value,
            depth=depth + 1,
        )

    if isinstance(value, Mapping):
        result: dict[str, object] = {}

        for key, item in list(
            value.items()
        )[:_MAX_COLLECTION_ITEMS]:
            if not isinstance(key, str) or not key:
                continue

            normalized = (
                key.strip()
                .casefold()
                .replace("-", "_")
                .replace(" ", "_")
            )

            if normalized in _FORBIDDEN_OUTPUT_KEYS:
                continue

            safe_item = _safe_json(
                item,
                depth=depth + 1,
            )

            if safe_item is not _DROP:
                result[key] = safe_item

        return result

    if (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
    ):
        return [
            _safe_json(
                item,
                depth=depth + 1,
            )
            for item in list(value)[
                :_MAX_COLLECTION_ITEMS
            ]
        ]

    return redact_sensitive(
        str(value)
    )[:_MAX_STRING_CHARS]


def _safe_text(
    value: object,
) -> str | None:
    if value is None:
        return None

    text = redact_sensitive(str(value)).strip()

    return (
        text[:_MAX_STRING_CHARS]
        if text
        else None
    )


__all__ = [
    "CanonicalActionExecutor",
    "evidence_execution_result",
]
