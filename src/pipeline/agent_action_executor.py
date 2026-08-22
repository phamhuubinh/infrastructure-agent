"""Execute one already-authorized Agent v2 capability through KnowledgeTool.

This bridge has no request interpretation or capability-selection role.  It
accepts only the typed output of the v2 validator, resolves that exact ID
against current KnowledgeTool metadata, and makes at most one dispatch.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import Enum

from src.pipeline.agent_action_validator import (
    AgentActionToolBudget,
    AgentActionValidationResult,
    AgentActionValidationStatus,
)
from src.pipeline.basic_calculator import (
    CalculatorContractResult,
    CalculatorResultStatus,
    calculate_request,
)
from src.pipeline.calculator_action_contract import CALCULATOR_CAPABILITY_ID
from src.pipeline.evidence_merge import EvidenceMerge
from src.pipeline.evidence_package import EvidencePackage
from src.pipeline.external_verification import ExternalVerificationExecutor
from src.pipeline.hard_request_constraints import HardRequestConstraints
from src.pipeline.internet_action_contract import InternetActionKind
from src.shared.execution.tool_result import ToolResult
from src.tool.capability_result import CapabilityStatus
from src.tool.errors import internal_error
from src.tool.knowledge_tool import KnowledgeTool


class AgentActionExecutionStatus(str, Enum):
    """Outcome of a single v2 bridge invocation."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"
    NOT_EXECUTED = "not_executed"


class AgentActionExecutionReason(str, Enum):
    """Safe reason for a bridge outcome without flattening tool failures."""

    DISPATCHED = "dispatched"
    VALIDATION_NOT_VALID = "validation_not_valid"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CAPABILITY_BINDING_UNAVAILABLE = "capability_binding_unavailable"
    CALCULATED = "calculated"


@dataclass(frozen=True, slots=True)
class AgentActionExecutionResult:
    """Immutable result of one approved v2 action execution attempt."""

    validation: AgentActionValidationResult
    status: AgentActionExecutionStatus
    reason: AgentActionExecutionReason
    budget: AgentActionToolBudget
    source_id: str | None = None
    tool_result: ToolResult | None = None
    evidence: EvidencePackage | None = None
    calculator_result: CalculatorContractResult | None = None
    dispatched: bool = False
    actual_tool_calls: int = 0
    calculator_calls: int = 0

    def __post_init__(self) -> None:
        if type(self.actual_tool_calls) is not int or self.actual_tool_calls < 0:
            raise ValueError("actual_tool_calls must be a non-negative integer.")
        if type(self.calculator_calls) is not int or self.calculator_calls < 0:
            raise ValueError("calculator_calls must be a non-negative integer.")

    @property
    def capability_id(self) -> str:
        return self.validation.capability_id

    @property
    def target_id(self) -> str | None:
        return self.validation.target_id

    @property
    def success(self) -> bool:
        return self.status is AgentActionExecutionStatus.SUCCESS


@dataclass(frozen=True, slots=True)
class _BoundRoute:
    source: str
    resource: str
    metadata: Mapping[str, object]


class AgentActionExecutor:
    """Dispatch exactly one valid v2 action through the reviewed tool boundary."""

    def __init__(
        self,
        knowledge_tool: KnowledgeTool,
        external_verification_executor: ExternalVerificationExecutor | None = None,
    ) -> None:
        if not isinstance(knowledge_tool, KnowledgeTool):
            raise TypeError("knowledge_tool must be a KnowledgeTool.")
        self._knowledge_tool = knowledge_tool
        self._evidence_merge = EvidenceMerge()
        self._external_verification = (
            external_verification_executor
            or ExternalVerificationExecutor(knowledge_tool)
        )

    def execute(
        self,
        validation: AgentActionValidationResult,
        budget: AgentActionToolBudget,
        *,
        raw_request: str | None = None,
        hard_constraints: HardRequestConstraints | None = None,
    ) -> AgentActionExecutionResult:
        """Execute one valid action, consuming the v2 budget only on dispatch."""

        if not isinstance(validation, AgentActionValidationResult):
            raise TypeError("validation must be an AgentActionValidationResult.")
        if not isinstance(budget, AgentActionToolBudget):
            raise TypeError("budget must be an AgentActionToolBudget.")
        if validation.status is not AgentActionValidationStatus.VALID:
            return self._not_executed(
                validation,
                budget,
                AgentActionExecutionReason.VALIDATION_NOT_VALID,
            )
        if not budget.permits_one_execution():
            return self._not_executed(
                validation,
                budget,
                AgentActionExecutionReason.BUDGET_EXHAUSTED,
            )

        if validation.capability_id == CALCULATOR_CAPABILITY_ID:
            return self._calculate(validation, budget)

        if validation.internet_request is not None:
            return self._execute_internet(
                validation,
                budget,
                raw_request=raw_request,
                hard_constraints=hard_constraints,
            )

        route = self._bind_exact_route(validation)
        if route is None:
            return self._not_executed(
                validation,
                budget,
                AgentActionExecutionReason.CAPABILITY_BINDING_UNAVAILABLE,
            )

        # All metadata and identity checks passed; the next operation is the
        # single approved high-level dispatch, so now consume the v2 counter.
        next_budget = budget.after_execution()
        arguments = {
            "source": route.source,
            "resource": route.resource,
            **dict(validation.normalized_arguments),
        }
        result = self._dispatch(route, arguments)
        evidence = self._evidence_merge.package_from_result(
            capability_name=validation.capability_id,
            evidence_name=validation.capability_id,
            result=result,
            target=validation.target_id or route.source,
        )
        return AgentActionExecutionResult(
            validation=validation,
            status=self._status_for(result),
            reason=AgentActionExecutionReason.DISPATCHED,
            budget=next_budget,
            source_id=route.source,
            tool_result=result,
            evidence=evidence,
            dispatched=True,
            actual_tool_calls=1,
        )

    @staticmethod
    def _calculate(
        validation: AgentActionValidationResult,
        budget: AgentActionToolBudget,
    ) -> AgentActionExecutionResult:
        request = validation.calculator_request
        if request is None:
            return AgentActionExecutor._not_executed(
                validation,
                budget,
                AgentActionExecutionReason.CAPABILITY_BINDING_UNAVAILABLE,
            )
        # This is the one authorized high-level v2 execution unit.  It does
        # not dispatch through KnowledgeTool or any Child Tool.
        next_budget = budget.after_execution()
        result = calculate_request(request)
        status = (
            AgentActionExecutionStatus.SUCCESS
            if result.status is CalculatorResultStatus.SUCCESS
            else AgentActionExecutionStatus.FAILURE
        )
        return AgentActionExecutionResult(
            validation=validation,
            status=status,
            reason=AgentActionExecutionReason.CALCULATED,
            budget=next_budget,
            calculator_result=result,
            dispatched=True,
            calculator_calls=1,
        )

    def _execute_internet(
        self,
        validation: AgentActionValidationResult,
        budget: AgentActionToolBudget,
        *,
        raw_request: str | None,
        hard_constraints: HardRequestConstraints | None,
    ) -> AgentActionExecutionResult:
        request = validation.internet_request
        source_id = validation.source_id
        if (
            request is None
            or source_id is None
            or not isinstance(raw_request, str)
            or not raw_request.strip()
            or not isinstance(hard_constraints, HardRequestConstraints)
        ):
            return self._not_executed(
                validation,
                budget,
                AgentActionExecutionReason.CAPABILITY_BINDING_UNAVAILABLE,
            )
        # The action budget is consumed once for the reviewed high-level
        # action, before its bounded internal search/fetch workflow begins.
        next_budget = budget.after_execution()
        if request.kind is InternetActionKind.CURRENT:
            outcome = self._external_verification.collect_current_action(
                source_id=source_id,
                query=request.query or "",
                user_request=raw_request,
                freshness_required=hard_constraints.requires_fresh_evidence,
            )
        else:
            outcome = self._external_verification.collect_url_action(
                source_id=source_id,
                url=request.url or "",
                user_request=raw_request,
                freshness_required=hard_constraints.requires_fresh_evidence,
            )
        evidence = self._external_verification.action_evidence(outcome)
        status = {
            CapabilityStatus.VALID: AgentActionExecutionStatus.SUCCESS,
            CapabilityStatus.VALID_EMPTY: AgentActionExecutionStatus.SUCCESS,
            CapabilityStatus.PARTIAL: AgentActionExecutionStatus.PARTIAL,
        }.get(evidence.capability_status, AgentActionExecutionStatus.FAILURE)
        return AgentActionExecutionResult(
            validation=validation,
            status=status,
            reason=AgentActionExecutionReason.DISPATCHED,
            budget=next_budget,
            source_id=source_id,
            evidence=evidence,
            dispatched=True,
            actual_tool_calls=outcome.search_calls + outcome.fetch_calls,
        )

    def _bind_exact_route(
        self, validation: AgentActionValidationResult
    ) -> _BoundRoute | None:
        category, separator, resource = validation.capability_id.partition(".")
        expected_source_kind = {
            "host": "linux",
            "grafana": "grafana",
            "zabbix": "zabbix",
            "internet": "internet",
        }.get(category)
        if (
            not separator
            or not resource
            or expected_source_kind is None
            or validation.source_family != expected_source_kind
        ):
            return None

        if category == "host":
            if validation.target_id is None:
                return None
            source = validation.target_id
        else:
            source = validation.source_id
            if source is None:
                return None
        return self._route_for_source(
            source,
            resource,
            expected_source_kind,
            self._knowledge_tool.get_capability_metadata(),
        )

    def _route_for_source(
        self,
        source: str,
        resource: str,
        expected_source_kind: str,
        metadata: Mapping[str, object],
    ) -> _BoundRoute | None:
        try:
            if self._knowledge_tool.source_kind(source) != expected_source_kind:
                return None
        except KeyError:
            return None
        entries = metadata.get(source)
        if not isinstance(entries, list):
            return None
        matching = tuple(
            entry
            for entry in entries
            if isinstance(entry, Mapping) and entry.get("name") == resource
        )
        # Metadata may contain one entry per operational cover while all of
        # them point at the same declared Child Tool resource.  The exact
        # (source, resource) pair remains unambiguous; this bridge never
        # promotes a different resource or source from that declaration.
        if not matching:
            return None
        return _BoundRoute(source, resource, matching[0])

    def _dispatch(self, route: _BoundRoute, arguments: dict[str, object]) -> ToolResult:
        try:
            result = self._knowledge_tool.execute(arguments)
            return replace(
                result,
                source=route.source,
                source_kind=self._knowledge_tool.source_kind(route.source),
                resource=route.resource,
                parameters=tuple(
                    sorted(
                        (str(key), value)
                        for key, value in arguments.items()
                        if key not in {"source", "resource"}
                    )
                ),
            )
        except (RuntimeError, ValueError, TypeError, OSError) as exc:
            message = f"KnowledgeTool dispatch failed for {route.resource}: {exc}"
            return ToolResult(
                success=False,
                error=message,
                capability_status=CapabilityStatus.COLLECTION_FAILED,
                capability_error=internal_error(message),
                source=route.source,
                source_kind=self._knowledge_tool.source_kind(route.source),
                resource=route.resource,
                parameters=tuple(
                    sorted(
                        (str(key), value)
                        for key, value in arguments.items()
                        if key not in {"source", "resource"}
                    )
                ),
            )

    @staticmethod
    def _not_executed(
        validation: AgentActionValidationResult,
        budget: AgentActionToolBudget,
        reason: AgentActionExecutionReason,
    ) -> AgentActionExecutionResult:
        return AgentActionExecutionResult(
            validation=validation,
            status=AgentActionExecutionStatus.NOT_EXECUTED,
            reason=reason,
            budget=budget,
        )

    @staticmethod
    def _status_for(result: ToolResult) -> AgentActionExecutionStatus:
        if result.capability_status is CapabilityStatus.PARTIAL:
            return AgentActionExecutionStatus.PARTIAL
        if result.success:
            return AgentActionExecutionStatus.SUCCESS
        return AgentActionExecutionStatus.FAILURE


__all__ = [
    "AgentActionExecutionReason",
    "AgentActionExecutionResult",
    "AgentActionExecutionStatus",
    "AgentActionExecutor",
]
