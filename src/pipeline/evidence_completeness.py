from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from src.pipeline.evidence_requirement import EvidenceRequirement
from src.pipeline.fact import Fact, FactFreshness, FactValidity
from src.pipeline.fact_set import FactSet
from src.pipeline.investigation_request import InvestigationRequest
from src.pipeline.temporal_evidence_guard import TemporalEvidenceGuard


class RequirementStatus(str, Enum):
    SATISFIED = "satisfied"
    MISSING = "missing"
    FAILED = "failed"
    STALE = "stale"
    CONTRADICTORY = "contradictory"
    UNSUPPORTED = "unsupported"
    SCHEMA_INVALID = "schema_invalid"


@dataclass(frozen=True, slots=True)
class RequirementEvaluation:
    requirement: str
    metric: str
    status: RequirementStatus
    fact_ids: tuple[str, ...] = ()
    explanation: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "requirement": self.requirement,
            "metric": self.metric,
            "status": self.status.value,
            "fact_ids": list(self.fact_ids),
            "explanation": self.explanation,
        }


@dataclass(frozen=True, slots=True)
class EvidenceCompletenessResult:
    evaluations: tuple[RequirementEvaluation, ...] = ()
    temporal_failures: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return not self.temporal_failures and all(
            item.status is RequirementStatus.SATISFIED for item in self.evaluations
        )

    @property
    def missing(self) -> tuple[str, ...]:
        names = [
            item.requirement
            for item in self.evaluations
            if item.status is not RequirementStatus.SATISFIED
        ]
        names.extend(self.temporal_failures)
        return tuple(dict.fromkeys(names))

    def statuses(self, status: RequirementStatus) -> tuple[str, ...]:
        return tuple(
            item.requirement for item in self.evaluations if item.status is status
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "complete": self.complete,
            "evaluations": [item.to_dict() for item in self.evaluations],
            "temporal_failures": list(self.temporal_failures),
        }


class EvidenceCompleteness:
    """Evaluate canonical required-fact contracts without AI."""

    def check(self, request: InvestigationRequest) -> EvidenceCompletenessResult:
        fact_set = request.fact_set
        if not fact_set and request.evidence:
            fact_set = FactSet.merge(*(package.facts for package in request.evidence))
            request.fact_set = fact_set
        evaluations = tuple(
            self._evaluate(requirement, request, fact_set)
            for requirement in request.required_evidence
        )
        temporal = TemporalEvidenceGuard().evaluate(request)
        result = EvidenceCompletenessResult(evaluations, temporal.failures)
        request.temporal_evidence_failures = temporal.failures
        request.evidence_complete = result.complete
        request.missing_evidence = result.missing
        request.evidence_completeness = result
        return result

    def _evaluate(
        self,
        requirement: EvidenceRequirement,
        request: InvestigationRequest,
        fact_set: FactSet,
    ) -> RequirementEvaluation:
        if not requirement.metric:
            return self._legacy_evaluate(requirement, request)

        candidates = list(fact_set.by_metric(requirement.metric))
        target = requirement.target or request.target
        if target:
            candidates = [fact for fact in candidates if fact.target == target]
        if requirement.subject:
            candidates = [
                fact for fact in candidates if fact.subject == requirement.subject
            ]
        candidates = [
            fact
            for fact in candidates
            if self._matches_parameters(fact, requirement.parameter_scope)
        ]
        if requirement.timeframe is not None:
            candidates = [
                fact
                for fact in candidates
                if requirement.timeframe.start
                <= int(fact.observed_at.timestamp())
                <= requirement.timeframe.end
            ]
        if not candidates:
            return RequirementEvaluation(
                requirement.name,
                requirement.metric,
                RequirementStatus.MISSING,
                explanation=(
                    f"no fact matched metric={requirement.metric}, "
                    f"target={target or '*'}, parameters={dict(requirement.parameter_scope)}"
                ),
            )

        contradictory = [
            fact for fact in candidates if fact.validity is FactValidity.CONTRADICTORY
        ]
        if contradictory:
            return self._result(
                requirement,
                RequirementStatus.CONTRADICTORY,
                contradictory,
                "matching sources report incompatible values",
            )

        stale = [
            fact
            for fact in candidates
            if fact.validity is FactValidity.STALE
            or fact.freshness is FactFreshness.STALE
            or (
                requirement.max_age_seconds is not None
                and fact.age_seconds() > requirement.max_age_seconds
            )
        ]
        usable = [
            fact
            for fact in candidates
            if (
                fact.validity in requirement.accepted_validities
                or (
                    requirement.allow_stale
                    and fact.validity is FactValidity.STALE
                )
            )
            and (requirement.allow_stale or fact not in stale)
        ]
        minimum = max(requirement.minimum_points, 1)
        if len(usable) >= minimum:
            return self._result(
                requirement,
                RequirementStatus.SATISFIED,
                usable,
                f"{len(usable)} matching canonical fact(s)",
            )
        if stale:
            return self._result(
                requirement,
                RequirementStatus.STALE,
                stale,
                "matching facts exceed the freshness contract",
            )
        invalidity_order = (
            (FactValidity.UNSUPPORTED, RequirementStatus.UNSUPPORTED),
            (FactValidity.SCHEMA_INVALID, RequirementStatus.SCHEMA_INVALID),
            (FactValidity.COMMAND_FAILED, RequirementStatus.FAILED),
            (FactValidity.NOT_COLLECTED, RequirementStatus.MISSING),
        )
        for validity, status in invalidity_order:
            failed = [fact for fact in candidates if fact.validity is validity]
            if failed:
                return self._result(
                    requirement,
                    status,
                    failed,
                    f"matching facts have validity={validity.value}",
                )
        return self._result(
            requirement,
            RequirementStatus.MISSING,
            candidates,
            f"needs {minimum} acceptable fact(s), found {len(usable)}",
        )

    @staticmethod
    def _matches_parameters(
        fact: Fact, scope: Mapping[str, object]
    ) -> bool:
        expected = dict(scope)
        if not expected:
            return True
        observed = {**fact.provenance.parameter_map, **dict(fact.dimensions)}
        aliases = {"name": "service_name", "query": "service_name"}
        for key, value in expected.items():
            actual = observed.get(key)
            if actual is None:
                actual = observed.get(aliases.get(str(key), ""))
            if actual is None and key == "service_name":
                actual = observed.get("name")
            if str(actual).removesuffix(".service") != str(value).removesuffix(
                ".service"
            ):
                return False
        return True

    @staticmethod
    def _result(
        requirement: EvidenceRequirement,
        status: RequirementStatus,
        facts: list[Fact],
        explanation: str,
    ) -> RequirementEvaluation:
        return RequirementEvaluation(
            requirement=requirement.name,
            metric=requirement.metric,
            status=status,
            fact_ids=tuple(sorted(fact.id for fact in facts)),
            explanation=explanation,
        )

    @staticmethod
    def _legacy_evaluate(
        requirement: EvidenceRequirement,
        request: InvestigationRequest,
    ) -> RequirementEvaluation:
        packages = [
            package
            for package in request.evidence
            if package.evidence_name == requirement.name
        ]
        valid = [package for package in packages if package.valid_for_requirements]
        if valid:
            return RequirementEvaluation(
                requirement.name,
                "",
                RequirementStatus.SATISFIED,
                explanation="legacy evidence-name contract",
            )
        if packages:
            return RequirementEvaluation(
                requirement.name,
                "",
                RequirementStatus.FAILED,
                explanation="legacy package collection failed",
            )
        return RequirementEvaluation(
            requirement.name,
            "",
            RequirementStatus.MISSING,
            explanation="legacy evidence package missing",
        )
