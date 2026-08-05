from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from src.pipeline.composite_rule import CompositeRule, WeightedCondition
from src.pipeline.fact import Fact, FactFreshness, FactValidity
from src.pipeline.fact_set import FactSet
from src.pipeline.finding import Finding, FindingDecision
from src.pipeline.provenance import claim_source_links


class ConditionState(str, Enum):
    SATISFIED = "satisfied"
    FALSE = "false"
    UNKNOWN = "unknown"
    STALE = "stale"
    COLLECTION_FAILED = "collection_failed"


@dataclass(frozen=True, slots=True)
class ConditionEvaluation:
    condition_id: str
    metric: str
    state: ConditionState
    weight: float
    required: bool
    fact_ids: tuple[str, ...] = ()
    confidence: float = 0.0
    explanation: str = ""

    @property
    def observable(self) -> bool:
        return self.state in {ConditionState.SATISFIED, ConditionState.FALSE}

    def to_dict(self) -> dict[str, Any]:
        return {
            "condition_id": self.condition_id,
            "metric": self.metric,
            "state": self.state.value,
            "weight": self.weight,
            "required": self.required,
            "fact_ids": list(self.fact_ids),
            "confidence": self.confidence,
            "explanation": self.explanation,
        }


@dataclass(frozen=True, slots=True)
class RuleEvaluation:
    rule: CompositeRule
    finding: Finding
    conditions: tuple[ConditionEvaluation, ...]

    @property
    def maximum_observable_score(self) -> float:
        return self.finding.maximum_observable_score

    @property
    def evidence_coverage(self) -> float:
        return self.finding.coverage


def compare(value: object, operator: str, threshold: object) -> bool:
    """Compare a canonical value without coercing collection failures to zero."""

    if isinstance(value, bool) or isinstance(threshold, bool):
        if operator == "eq":
            return value is threshold
        if operator == "ne":
            return value is not threshold
        return False
    if operator in {"gt", "ge", "lt", "le"}:
        if not isinstance(value, (int, float)) or not isinstance(
            threshold, (int, float)
        ):
            return False
        if operator == "gt":
            return value > threshold
        if operator == "ge":
            return value >= threshold
        if operator == "lt":
            return value < threshold
        return value <= threshold
    if operator == "eq":
        return value == threshold
    if operator == "ne":
        return value != threshold
    raise ValueError(f"unsupported operator: {operator}")


class RuleEngine:
    """Evaluate weighted rules over immutable canonical facts."""

    def evaluate_condition(
        self,
        condition: WeightedCondition,
        fact_set: FactSet,
        *,
        target: str | None = None,
    ) -> ConditionEvaluation:
        candidates = list(
            fact_set.query(
                metric=condition.metric,
                target=condition.target or target,
                subject=condition.subject,
            )
        )
        if not candidates:
            return self._condition_result(
                condition,
                ConditionState.UNKNOWN,
                explanation="canonical fact was not collected",
            )

        failed = [
            fact
            for fact in candidates
            if fact.validity
            in {
                FactValidity.COMMAND_FAILED,
                FactValidity.UNSUPPORTED,
                FactValidity.SCHEMA_INVALID,
                FactValidity.CONTRADICTORY,
            }
        ]
        fresh_usable = [
            fact
            for fact in candidates
            if fact.validity in {FactValidity.VALID, FactValidity.VALID_EMPTY}
            and fact.freshness is not FactFreshness.STALE
            and (
                condition.max_age_seconds is None
                or fact.age_seconds() <= condition.max_age_seconds
            )
        ]
        stale = [
            fact
            for fact in candidates
            if fact.validity is FactValidity.STALE
            or fact.freshness is FactFreshness.STALE
            or (
                condition.max_age_seconds is not None
                and fact.age_seconds() > condition.max_age_seconds
            )
        ]
        if not fresh_usable:
            if failed:
                return self._condition_result(
                    condition,
                    ConditionState.COLLECTION_FAILED,
                    facts=failed,
                    explanation="matching fact collection failed or contradicted",
                )
            if stale:
                return self._condition_result(
                    condition,
                    ConditionState.STALE,
                    facts=stale,
                    explanation="matching facts are stale",
                )
            return self._condition_result(
                condition,
                ConditionState.UNKNOWN,
                facts=candidates,
                explanation="matching facts are not observable",
            )

        satisfied = [
            fact
            for fact in fresh_usable
            if fact.validity is FactValidity.VALID
            and compare(fact.value, condition.operator, condition.threshold)
        ]
        if satisfied:
            return self._condition_result(
                condition,
                ConditionState.SATISFIED,
                facts=satisfied,
                explanation=(
                    f"{condition.metric} {condition.operator} {condition.threshold}"
                ),
            )
        return self._condition_result(
            condition,
            ConditionState.FALSE,
            facts=fresh_usable,
            explanation=(
                f"no observed {condition.metric} value satisfied "
                f"{condition.operator} {condition.threshold}"
            ),
        )

    def evaluate_rule(
        self,
        rule: CompositeRule,
        fact_set: FactSet,
        *,
        target: str | None = None,
    ) -> RuleEvaluation:
        evaluations = tuple(
            self.evaluate_condition(condition, fact_set, target=target)
            for condition in rule.conditions
        )
        total_weight = rule.total_weight
        raw_score = sum(
            item.weight
            for item in evaluations
            if item.state is ConditionState.SATISFIED
        )
        observable_weight = sum(
            item.weight for item in evaluations if item.observable
        )
        missing_weight = total_weight - observable_weight
        coverage = observable_weight / total_weight
        score = raw_score
        if rule.renormalize_missing and observable_weight:
            score = raw_score * total_weight / observable_weight

        required_unavailable = any(
            item.required
            and item.state
            in {
                ConditionState.UNKNOWN,
                ConditionState.STALE,
                ConditionState.COLLECTION_FAILED,
            }
            for item in evaluations
        )
        maximum_possible = raw_score + missing_weight
        if (
            score >= rule.decision_threshold
            and not required_unavailable
            and coverage >= rule.minimum_coverage
        ):
            decision = FindingDecision.SUPPORTED
        elif maximum_possible < rule.decision_threshold:
            decision = FindingDecision.NOT_SUPPORTED
        elif required_unavailable or missing_weight > 0 or coverage < rule.minimum_coverage:
            decision = FindingDecision.INSUFFICIENT_EVIDENCE
        else:
            decision = FindingDecision.NOT_SUPPORTED

        supporting = tuple(
            sorted(
                fact_id
                for item in evaluations
                if item.state is ConditionState.SATISFIED
                for fact_id in item.fact_ids
            )
        )
        contradicting = tuple(
            sorted(
                fact_id
                for item in evaluations
                if item.state is ConditionState.FALSE
                for fact_id in item.fact_ids
            )
        )
        missing = tuple(
            item.metric
            for item in evaluations
            if item.state
            in {
                ConditionState.UNKNOWN,
                ConditionState.STALE,
                ConditionState.COLLECTION_FAILED,
            }
        )
        linked_ids = set(supporting) | set(contradicting)
        linked_facts = tuple(fact for fact in fact_set if fact.id in linked_ids)
        if observable_weight:
            observed_confidence = sum(
                item.weight * item.confidence
                for item in evaluations
                if item.observable
            ) / observable_weight
        else:
            observed_confidence = 0.0
        confidence = observed_confidence * coverage
        finding = Finding(
            id=f"finding:{rule.id}:{target or 'all'}",
            type=rule.type,
            score=score,
            decision=decision,
            severity=rule.severity,
            supporting_fact_ids=supporting,
            contradicting_fact_ids=contradicting,
            missing_facts=tuple(dict.fromkeys(missing)),
            confidence=confidence,
            coverage=coverage,
            maximum_observable_score=observable_weight,
            maximum_possible_score=maximum_possible,
            rule_id=rule.id,
            rule_version=rule.version,
            source_links=claim_source_links(linked_facts),
            explanation=self._explanation(
                rule, decision, raw_score, observable_weight, coverage
            ),
        )
        return RuleEvaluation(rule=rule, finding=finding, conditions=evaluations)

    def evaluate(
        self,
        rules: tuple[CompositeRule, ...] | list[CompositeRule],
        fact_set: FactSet,
    ) -> tuple[Finding, ...]:
        """Evaluate applicable rules per target in stable order.

        A completely unrelated rule is omitted.  Once at least one of its
        metrics is present, all its missing conditions remain visible in the
        resulting finding.
        """

        return tuple(
            evaluation.finding
            for evaluation in self.evaluate_details(rules, fact_set)
        )

    def evaluate_details(
        self,
        rules: tuple[CompositeRule, ...] | list[CompositeRule],
        fact_set: FactSet,
    ) -> tuple[RuleEvaluation, ...]:
        """Return findings with condition states for evidence expansion."""

        evaluations: list[RuleEvaluation] = []
        targets = sorted({fact.target for fact in fact_set})
        for rule in sorted(rules, key=lambda item: item.id):
            rule_metrics = {condition.metric for condition in rule.conditions}
            for target in targets:
                target_facts = fact_set.by_target(target)
                if not any(fact.metric in rule_metrics for fact in target_facts):
                    continue
                evaluations.append(self.evaluate_rule(rule, fact_set, target=target))
        return tuple(evaluations)

    @staticmethod
    def _condition_result(
        condition: WeightedCondition,
        state: ConditionState,
        *,
        facts: list[Fact] | tuple[Fact, ...] = (),
        explanation: str,
    ) -> ConditionEvaluation:
        confidence = min((fact.confidence for fact in facts), default=0.0)
        return ConditionEvaluation(
            condition_id=condition.id,
            metric=condition.metric,
            state=state,
            weight=condition.weight,
            required=condition.required,
            fact_ids=tuple(sorted(fact.id for fact in facts)),
            confidence=confidence,
            explanation=explanation,
        )

    @staticmethod
    def _explanation(
        rule: CompositeRule,
        decision: FindingDecision,
        score: float,
        observable: float,
        coverage: float,
    ) -> str:
        policy = "explicit missing-weight renormalization" if rule.renormalize_missing else "no missing-weight renormalization"
        return (
            f"rule={rule.id}@{rule.version}; decision={decision.value}; "
            f"score={score:.3f}/{rule.decision_threshold:.3f}; "
            f"observable_weight={observable:.3f}/{rule.total_weight:.3f}; "
            f"coverage={coverage:.3f}; policy={policy}"
        )
