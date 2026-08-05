from __future__ import annotations

from collections.abc import Iterable

from src.pipeline.composite_rule import CompositeRule
from src.pipeline.fact_set import FactSet
from src.pipeline.finding import Finding
from src.pipeline.rule_engine import RuleEngine, RuleEvaluation
from src.pipeline.threshold_evaluator import ThresholdEvaluator
from src.shared.config_schema import load_rule_configs


def configured_composite_rules() -> tuple[CompositeRule, ...]:
    return tuple(
        rule.to_domain()
        for config in load_rule_configs()
        for rule in config.composite_rules
    )


class EvidenceCorrelation:
    """Convert cross-source canonical observations into versioned findings."""

    def __init__(self, rules: tuple[CompositeRule, ...] | None = None) -> None:
        self.rules = rules if rules is not None else configured_composite_rules()
        self._engine = RuleEngine()
        self._thresholds = ThresholdEvaluator()

    def correlate_facts(
        self,
        fact_set: FactSet,
        atomic_findings: Iterable[Finding] = (),
    ) -> tuple[Finding, ...]:
        """Evaluate reviewed composite rules over facts, never raw dictionaries."""

        # Materialize to make this boundary explicit and deterministic. Atomic
        # findings are accepted for callers that carry both flow artifacts;
        # composite conditions still resolve their provenance from FactSet.
        tuple(atomic_findings)
        enriched = self._thresholds.derive_facts(fact_set)
        return self._engine.evaluate(self.rules, enriched)

    def evaluate_facts(self, fact_set: FactSet) -> tuple[RuleEvaluation, ...]:
        enriched = self._thresholds.derive_facts(fact_set)
        return self._engine.evaluate_details(self.rules, enriched)

    def correlate(
        self,
        evidence_or_facts: FactSet | list,
        threshold_eval: dict[str, str] | None = None,
    ) -> tuple[Finding, ...] | list[dict[str, str]]:
        """Canonical API plus a bounded adapter for legacy callers."""

        if isinstance(evidence_or_facts, FactSet):
            return self.correlate_facts(evidence_or_facts)
        return self._legacy_correlate(threshold_eval or {})

    @staticmethod
    def _legacy_correlate(
        threshold_eval: dict[str, str],
    ) -> list[dict[str, str]]:
        findings: list[dict[str, str]] = []
        severity_names = set(threshold_eval)
        if "CPU" in severity_names and "Load" in severity_names:
            findings.append(
                {
                    "type": "resource_bottleneck",
                    "items": "CPU, Load",
                    "description": (
                        "High CPU usage combined with elevated per-core load "
                        "supports a CPU bottleneck."
                    ),
                }
            )
        if "Memory" in severity_names or "Swap" in severity_names:
            findings.append(
                {
                    "type": "memory_pressure",
                    "items": "Memory, Swap",
                    "description": (
                        "High memory or swap usage is an observable memory "
                        "pressure signal."
                    ),
                }
            )
        if ("Storage" in severity_names or "Disk" in severity_names) and (
            "Memory" in severity_names or "CPU" in severity_names
        ):
            findings.append(
                {
                    "type": "system_overload",
                    "items": "Storage, Memory/CPU",
                    "description": (
                        "Pressure across multiple resource domains supports "
                        "overall system overload."
                    ),
                }
            )
        return findings
