from __future__ import annotations

from dataclasses import dataclass

from src.pipeline.composite_rule import CompositeRule, WeightedCondition
from src.pipeline.fact import Fact, FactFreshness, FactValidity
from src.pipeline.fact_set import FactSet
from src.pipeline.finding import Finding, FindingDecision
from src.pipeline.provenance import Provenance
from src.pipeline.rule_engine import RuleEngine


@dataclass(frozen=True, slots=True)
class AtomicRule:
    id: str
    metric: str
    operator: str
    threshold: float
    severity: str
    version: str = "1.0.0"
    required_context: tuple[str, ...] = ()
    owner: str = "orion-core"
    rationale: str = "Operational threshold reviewed by Orion maintainers."
    source_cases: tuple[str, ...] = ("DR1-601",)

    def as_composite(self) -> CompositeRule:
        return CompositeRule(
            id=self.id,
            type="atomic_threshold",
            conditions=(
                WeightedCondition(
                    id=f"{self.id}.threshold",
                    metric=self.metric,
                    operator=self.operator,
                    threshold=self.threshold,
                    weight=1.0,
                ),
            ),
            decision_threshold=1.0,
            severity=self.severity,
            version=self.version,
            owner=self.owner,
            rationale=self.rationale,
            source_cases=self.source_cases,
            minimum_coverage=1.0,
        )


DEFAULT_ATOMIC_RULES: tuple[AtomicRule, ...] = (
    AtomicRule("cpu.usage.critical", "cpu.usage", "gt", 90.0, "critical"),
    AtomicRule("cpu.usage.warning", "cpu.usage", "gt", 80.0, "warning"),
    AtomicRule(
        "cpu.load_per_core.critical", "cpu.load_per_core", "gt", 2.0, "critical"
    ),
    AtomicRule(
        "cpu.load_per_core.warning", "cpu.load_per_core", "gt", 1.0, "warning"
    ),
    AtomicRule(
        "memory.usage.critical", "memory.usage", "gt", 90.0, "critical"
    ),
    AtomicRule("memory.usage.warning", "memory.usage", "gt", 80.0, "warning"),
    AtomicRule("swap.usage.critical", "swap.usage", "gt", 80.0, "critical"),
    AtomicRule("swap.usage.warning", "swap.usage", "gt", 50.0, "warning"),
    AtomicRule(
        "filesystem.usage.critical",
        "filesystem.usage",
        "gt",
        90.0,
        "critical",
    ),
    AtomicRule(
        "filesystem.usage.warning", "filesystem.usage", "gt", 80.0, "warning"
    ),
    AtomicRule(
        "filesystem.inode_usage.critical",
        "filesystem.inode_usage",
        "gt",
        90.0,
        "critical",
    ),
    AtomicRule(
        "filesystem.inode_usage.warning",
        "filesystem.inode_usage",
        "gt",
        80.0,
        "warning",
    ),
    AtomicRule(
        "process.zombie_count.warning",
        "process.zombie_count",
        "gt",
        0.0,
        "warning",
    ),
)


class ThresholdEvaluator:
    """Evaluate reviewed atomic rules over valid, fresh canonical facts."""

    _LEGACY_METRICS = {
        "cpu_usage": "cpu.usage",
        "memory_usage": "memory.usage",
        "memory_usage_pct": "memory.usage",
        "swap_used_pct": "swap.usage",
        "swap_usage": "swap.usage",
        "usage_percent": "filesystem.usage",
        "used_pct": "filesystem.usage",
        "zombie_count": "process.zombie_count",
        "zombies": "process.zombie_count",
    }

    def __init__(self, rules: tuple[AtomicRule, ...] | None = None) -> None:
        self.rules = rules or DEFAULT_ATOMIC_RULES
        self._engine = RuleEngine()

    def derive_facts(self, fact_set: FactSet) -> FactSet:
        """Add ``cpu.load_per_core`` without mutating the collected FactSet."""

        derived: list[Fact] = []
        for target in sorted({fact.target for fact in fact_set}):
            load = self._latest_usable(fact_set, "system.load_1m", target)
            cores = self._latest_usable(fact_set, "cpu.logical_cores", target)
            if load is None or cores is None:
                continue
            if (
                not isinstance(load.value, (int, float))
                or isinstance(load.value, bool)
                or not isinstance(cores.value, (int, float))
                or isinstance(cores.value, bool)
                or cores.value <= 0
            ):
                continue
            observed = max(load.observed_at, cores.observed_at)
            collected = max(load.collected_at, cores.collected_at)
            provenance = Provenance(
                source="derived",
                capability="derive.cpu.load_per_core",
                target=target,
                observed_at=observed,
                command_ids=tuple(
                    dict.fromkeys(
                        load.provenance.command_ids + cores.provenance.command_ids
                    )
                ),
                parameters=(("input_fact_ids", (load.id, cores.id)),),
                schema_version="reasoning.v1",
            )
            derived.append(
                Fact(
                    subject="system",
                    metric="cpu.load_per_core",
                    value=float(load.value) / float(cores.value),
                    unit="load_per_core",
                    observed_at=observed,
                    collected_at=collected,
                    source="derived",
                    target=target,
                    validity=FactValidity.VALID,
                    freshness=FactFreshness.FRESH,
                    confidence=min(load.confidence, cores.confidence),
                    provenance=provenance,
                    dimensions={"input_fact_ids": (load.id, cores.id)},
                )
            )
        return FactSet.merge(fact_set, derived)

    def evaluate_fact_set(self, fact_set: FactSet) -> tuple[Finding, ...]:
        enriched = self.derive_facts(fact_set)
        findings: list[Finding] = []
        targets = sorted({fact.target for fact in enriched})
        for rule in sorted(self.rules, key=lambda item: item.id):
            for target in targets:
                if not enriched.query(metric=rule.metric, target=target):
                    continue
                evaluation = self._engine.evaluate_rule(
                    rule.as_composite(), enriched, target=target
                )
                finding = evaluation.finding
                if rule.required_context:
                    missing = tuple(
                        metric
                        for metric in rule.required_context
                        if not any(
                            fact.usable
                            for fact in enriched.query(metric=metric, target=target)
                        )
                    )
                    if missing:
                        finding = Finding(
                            id=finding.id,
                            type=finding.type,
                            score=finding.score,
                            decision=FindingDecision.INSUFFICIENT_EVIDENCE,
                            severity=finding.severity,
                            supporting_fact_ids=finding.supporting_fact_ids,
                            contradicting_fact_ids=finding.contradicting_fact_ids,
                            missing_facts=finding.missing_facts + missing,
                            confidence=finding.confidence,
                            rule_version=finding.rule_version,
                            rule_id=finding.rule_id,
                            coverage=finding.coverage,
                            maximum_observable_score=finding.maximum_observable_score,
                            maximum_possible_score=finding.maximum_possible_score,
                            source_links=finding.source_links,
                            explanation=finding.explanation
                            + "; required context unavailable",
                        )
                findings.append(finding)
        return tuple(findings)

    def highest_severity(self, fact_set: FactSet) -> str | None:
        supported = [
            finding.severity
            for finding in self.evaluate_fact_set(fact_set)
            if finding.decision is FindingDecision.SUPPORTED
        ]
        return max(supported, key=_severity_rank) if supported else None

    def evaluate(self, data: dict) -> str | None:
        """Compatibility adapter for pre-canonical callers.

        Production reasoning uses :meth:`evaluate_fact_set`.  This bounded
        adapter exists while old integrations still submit one normalized
        collector dict.
        """

        if not isinstance(data, dict):
            return None
        severities: list[str] = []
        for raw_key, metric in self._LEGACY_METRICS.items():
            value = _extract_nested(data, raw_key)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            for rule in self.rules:
                if rule.metric != metric:
                    continue
                if _compare(float(value), rule.operator, rule.threshold):
                    severities.append(rule.severity)
        # Legacy load is made per-core when context is available.  With no
        # core count we keep historical thresholds only in this adapter.
        load = _extract_nested(data, "load_1min")
        cores = _extract_nested(data, "logical_cores") or _extract_nested(
            data, "cores"
        )
        if isinstance(load, (int, float)) and not isinstance(load, bool):
            normalized = (
                float(load) / float(cores)
                if isinstance(cores, (int, float))
                and not isinstance(cores, bool)
                and cores > 0
                else float(load) / 4.0
            )
            if normalized > 2.0:
                severities.append("critical")
            elif normalized > 1.0:
                severities.append("warning")
        return max(severities, key=_severity_rank) if severities else None

    def evaluate_all(self, evidence_list: list) -> dict[str, str]:
        result: dict[str, str] = {}
        for package in evidence_list:
            facts = tuple(getattr(package, "facts", ()))
            if facts:
                severity = self.highest_severity(FactSet(facts))
            elif getattr(package, "success", False):
                data = getattr(package, "data", None)
                severity = self.evaluate(data) if isinstance(data, dict) else None
            else:
                severity = None
            if severity:
                result[str(getattr(package, "evidence_name", "unknown"))] = severity
        return result

    @staticmethod
    def _latest_usable(
        fact_set: FactSet, metric: str, target: str
    ) -> Fact | None:
        candidates = [
            fact
            for fact in fact_set.query(metric=metric, target=target)
            if fact.validity is FactValidity.VALID
            and fact.freshness is FactFreshness.FRESH
        ]
        return max(candidates, key=lambda fact: (fact.observed_at, fact.id), default=None)


def _severity_rank(severity: str) -> int:
    return {"info": 0, "warning": 1, "critical": 2}.get(severity, -1)


def _compare(value: float, operator: str, threshold: float) -> bool:
    if operator == "gt":
        return value > threshold
    if operator == "ge":
        return value >= threshold
    if operator == "lt":
        return value < threshold
    if operator == "le":
        return value <= threshold
    if operator == "eq":
        return value == threshold
    if operator == "ne":
        return value != threshold
    raise ValueError(f"unsupported operator: {operator}")


def _extract_nested(data: dict, key: str) -> object | None:
    current: object = data
    for part in key.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if current is None:
            return None
    return current
