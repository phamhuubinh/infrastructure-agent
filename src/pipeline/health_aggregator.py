from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from src.pipeline.evidence_completeness import (
    EvidenceCompletenessResult,
    RequirementStatus,
)
from src.pipeline.fact import Fact, FactValidity
from src.pipeline.fact_set import FactSet
from src.pipeline.finding import Finding, FindingDecision


class HealthStatus(str, Enum):
    CRITICAL = "critical"
    UNAVAILABLE = "unavailable"
    WARNING = "warning"
    HEALTHY = "healthy"


_PRIORITY = {
    HealthStatus.HEALTHY: 0,
    HealthStatus.WARNING: 1,
    HealthStatus.UNAVAILABLE: 2,
    HealthStatus.CRITICAL: 3,
}


@dataclass(frozen=True, slots=True)
class TargetHealth:
    target: str
    status: HealthStatus
    active_incident_fact_ids: tuple[str, ...] = ()
    finding_ids: tuple[str, ...] = ()
    unavailable_requirements: tuple[str, ...] = ()
    confirmed_healthy_fact_ids: tuple[str, ...] = ()
    explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "status": self.status.value,
            "active_incident_fact_ids": list(self.active_incident_fact_ids),
            "finding_ids": list(self.finding_ids),
            "unavailable_requirements": list(self.unavailable_requirements),
            "confirmed_healthy_fact_ids": list(self.confirmed_healthy_fact_ids),
            "explanation": self.explanation,
        }


@dataclass(frozen=True, slots=True)
class HealthSummary:
    status: HealthStatus
    targets: tuple[TargetHealth, ...]
    incomplete_evidence: tuple[str, ...] = ()

    @property
    def healthy(self) -> bool:
        return self.status is HealthStatus.HEALTHY

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "targets": [target.to_dict() for target in self.targets],
            "incomplete_evidence": list(self.incomplete_evidence),
        }


class HealthAggregator:
    """Aggregate health with incidents and evidence gaps taking precedence."""

    def aggregate(
        self,
        fact_set: FactSet,
        findings: tuple[Finding, ...] | list[Finding] = (),
        completeness: EvidenceCompletenessResult | None = None,
        *,
        default_target: str = "localhost",
    ) -> HealthSummary:
        targets = sorted({fact.target for fact in fact_set} or {default_target})
        unavailable = self._unavailable(completeness)
        target_results = tuple(
            self._target_health(
                target,
                fact_set,
                tuple(findings),
                unavailable if len(targets) == 1 else (),
                completeness,
            )
            for target in targets
        )
        status = max(target_results, key=lambda item: _PRIORITY[item.status]).status
        # Requirements currently carry a request/default target. Preserve the
        # gap globally when a multi-target investigation cannot attribute it.
        if unavailable and len(targets) > 1 and status is not HealthStatus.CRITICAL:
            status = HealthStatus.UNAVAILABLE
        return HealthSummary(status, target_results, unavailable)

    def _target_health(
        self,
        target: str,
        fact_set: FactSet,
        findings: tuple[Finding, ...],
        unavailable: tuple[str, ...],
        completeness: EvidenceCompletenessResult | None,
    ) -> TargetHealth:
        target_facts = fact_set.by_target(target)
        critical_incidents = tuple(
            sorted(
                fact.id
                for fact in target_facts
                if self._incident_level(fact) == "critical"
            )
        )
        warning_incidents = tuple(
            sorted(
                fact.id
                for fact in target_facts
                if self._incident_level(fact) == "warning"
            )
        )
        if critical_incidents:
            return TargetHealth(
                target,
                HealthStatus.CRITICAL,
                active_incident_fact_ids=critical_incidents,
                explanation="active critical monitoring incident(s) take health priority",
            )
        if unavailable:
            return TargetHealth(
                target,
                HealthStatus.UNAVAILABLE,
                unavailable_requirements=unavailable,
                explanation="critical health evidence is incomplete or unavailable",
            )
        target_findings = tuple(
            finding
            for finding in findings
            if finding.decision is FindingDecision.SUPPORTED
            and self._finding_targets(finding, fact_set, target)
        )
        if target_findings or warning_incidents:
            status = (
                HealthStatus.CRITICAL
                if any(finding.severity == "critical" for finding in target_findings)
                else HealthStatus.WARNING
            )
            return TargetHealth(
                target,
                status,
                active_incident_fact_ids=warning_incidents,
                finding_ids=tuple(sorted(finding.id for finding in target_findings)),
                explanation="active warning incident or supported finding(s)",
            )
        confirmed = tuple(
            sorted(
                fact.id
                for fact in target_facts
                if fact.usable and not self._active_incident(fact)
            )
        )
        complete = completeness is None or completeness.complete
        if complete and confirmed:
            return TargetHealth(
                target,
                HealthStatus.HEALTHY,
                confirmed_healthy_fact_ids=confirmed,
                explanation="no incident or supported warning in complete evidence",
            )
        return TargetHealth(
            target,
            HealthStatus.UNAVAILABLE,
            unavailable_requirements=("health evidence",),
            explanation="health cannot be confirmed from available evidence",
        )

    @staticmethod
    def _unavailable(
        completeness: EvidenceCompletenessResult | None,
    ) -> tuple[str, ...]:
        if completeness is None:
            return ()
        unavailable_states = {
            RequirementStatus.MISSING,
            RequirementStatus.FAILED,
            RequirementStatus.STALE,
            RequirementStatus.CONTRADICTORY,
            RequirementStatus.UNSUPPORTED,
            RequirementStatus.SCHEMA_INVALID,
        }
        names = [
            evaluation.requirement
            for evaluation in completeness.evaluations
            if evaluation.status in unavailable_states
        ]
        names.extend(completeness.temporal_failures)
        return tuple(dict.fromkeys(names))

    @staticmethod
    def _active_incident(fact: Fact) -> bool:
        if fact.validity is not FactValidity.VALID:
            return False
        if fact.metric in {"monitoring.problem_active", "monitoring.trigger_active"}:
            value = fact.value
            return isinstance(value, Mapping) and value.get("active") is True
        if fact.metric == "monitoring.agent_availability":
            return str(fact.value) == "2"
        return False

    @classmethod
    def _incident_level(cls, fact: Fact) -> str | None:
        if not cls._active_incident(fact):
            return None
        if fact.metric == "monitoring.agent_availability":
            return "critical"
        value = fact.value
        severity: object = None
        if isinstance(value, Mapping):
            severity = value.get("severity_code", value.get("severity"))
        if isinstance(severity, str):
            normalized = severity.casefold()
            if normalized in {"4", "5", "high", "disaster", "critical"}:
                return "critical"
        if isinstance(severity, (int, float)) and severity >= 4:
            return "critical"
        return "warning"

    @staticmethod
    def _finding_targets(finding: Finding, fact_set: FactSet, target: str) -> bool:
        ids = set(finding.supporting_fact_ids) | set(finding.contradicting_fact_ids)
        if any(fact.id in ids and fact.target == target for fact in fact_set):
            return True
        return finding.id.endswith(f":{target}")
