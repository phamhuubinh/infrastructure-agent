from __future__ import annotations

from dataclasses import dataclass

from src.pipeline.finding import Finding, FindingDecision
from src.pipeline.rule_engine import ConditionState, RuleEvaluation


@dataclass(frozen=True, slots=True)
class MetricCapability:
    metric: str
    capability: str
    evidence_name: str
    expected_reliability: float
    estimated_cost: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.expected_reliability <= 1.0:
            raise ValueError("expected_reliability must be between 0.0 and 1.0")
        if self.estimated_cost <= 0:
            raise ValueError("estimated_cost must be positive")


@dataclass(frozen=True, slots=True)
class ExpansionCandidate:
    metric: str
    capability: str
    evidence_name: str
    condition_weight: float
    expected_reliability: float
    estimated_cost: float
    priority: float
    reason: str


DEFAULT_METRIC_CAPABILITIES: tuple[MetricCapability, ...] = (
    MetricCapability("cpu.usage", "CPU Utilization", "CPU Usage", 0.9, 0.2),
    MetricCapability(
        "cpu.logical_cores", "CPU Information", "CPU Hardware", 0.95, 0.1
    ),
    MetricCapability(
        "system.load_1m", "System Load Assessment", "Load Average", 0.95, 0.1
    ),
    MetricCapability(
        "cpu.load_per_core", "CPU Information", "CPU Runtime", 0.9, 0.2
    ),
    MetricCapability("cpu.iowait", "CPU Utilization", "CPU Usage", 0.9, 0.2),
    MetricCapability(
        "memory.usage", "Memory Utilization", "Memory Usage", 0.95, 0.1
    ),
    MetricCapability("swap.usage", "Swap Information", "Swap", 0.95, 0.1),
    MetricCapability(
        "filesystem.usage", "Disk Utilization", "Disk Usage", 0.95, 0.2
    ),
    MetricCapability(
        "filesystem.inode_usage",
        "Filesystem Inode Utilization",
        "Filesystem Inodes",
        0.85,
        0.2,
    ),
    MetricCapability(
        "monitoring.problem_active",
        "Monitoring Problems",
        "Active Problems",
        0.9,
        0.2,
    ),
)


class EvidenceExpander:
    """Select at most two valuable missing facts with a deterministic score."""

    def __init__(
        self,
        mappings: tuple[MetricCapability, ...] | None = None,
        *,
        max_selection: int = 2,
    ) -> None:
        if max_selection not in {1, 2}:
            raise ValueError("max_selection must be 1 or 2")
        self.max_selection = max_selection
        self._mappings = {
            mapping.metric: mapping
            for mapping in (mappings or DEFAULT_METRIC_CAPABILITIES)
        }

    def select(
        self,
        evaluations: tuple[RuleEvaluation, ...] | list[RuleEvaluation],
        *,
        already_planned: set[str] | None = None,
        limit: int | None = None,
    ) -> tuple[ExpansionCandidate, ...]:
        planned = already_planned or set()
        by_capability: dict[str, ExpansionCandidate] = {}
        for evaluation in evaluations:
            if evaluation.finding.decision is not FindingDecision.INSUFFICIENT_EVIDENCE:
                continue
            # Do not expand an unrelated all-missing rule. At least one
            # condition must already be observable.
            if evaluation.evidence_coverage <= 0:
                continue
            for condition in evaluation.conditions:
                if condition.state not in {
                    ConditionState.UNKNOWN,
                    ConditionState.STALE,
                    ConditionState.COLLECTION_FAILED,
                }:
                    continue
                mapping = self._mappings.get(condition.metric)
                if mapping is None or mapping.capability in planned:
                    continue
                priority = (
                    condition.weight
                    * mapping.expected_reliability
                    / mapping.estimated_cost
                )
                candidate = ExpansionCandidate(
                    metric=condition.metric,
                    capability=mapping.capability,
                    evidence_name=mapping.evidence_name,
                    condition_weight=condition.weight,
                    expected_reliability=mapping.expected_reliability,
                    estimated_cost=mapping.estimated_cost,
                    priority=priority,
                    reason=(
                        f"missing {condition.metric} for {evaluation.rule.id}; "
                        f"priority={condition.weight}*"
                        f"{mapping.expected_reliability}/{mapping.estimated_cost}"
                    ),
                )
                current = by_capability.get(mapping.capability)
                if current is None or self._sort_key(candidate) < self._sort_key(
                    current
                ):
                    by_capability[mapping.capability] = candidate
        selection_limit = min(limit or self.max_selection, self.max_selection)
        return tuple(
            sorted(by_capability.values(), key=self._sort_key)[:selection_limit]
        )

    def select_from_findings(
        self,
        findings: tuple[Finding, ...] | list[Finding],
        *,
        already_planned: set[str] | None = None,
        condition_weights: dict[str, float] | None = None,
        limit: int | None = None,
    ) -> tuple[ExpansionCandidate, ...]:
        """Select when only serialized Finding artifacts are available."""

        planned = already_planned or set()
        weights = condition_weights or {}
        candidates: dict[str, ExpansionCandidate] = {}
        for finding in findings:
            if (
                finding.decision is not FindingDecision.INSUFFICIENT_EVIDENCE
                or finding.coverage <= 0
            ):
                continue
            for metric in finding.missing_facts:
                mapping = self._mappings.get(metric)
                if mapping is None or mapping.capability in planned:
                    continue
                weight = weights.get(metric, 1.0)
                priority = weight * mapping.expected_reliability / mapping.estimated_cost
                candidate = ExpansionCandidate(
                    metric,
                    mapping.capability,
                    mapping.evidence_name,
                    weight,
                    mapping.expected_reliability,
                    mapping.estimated_cost,
                    priority,
                    f"missing {metric} for {finding.rule_id}",
                )
                current = candidates.get(mapping.capability)
                if current is None or self._sort_key(candidate) < self._sort_key(
                    current
                ):
                    candidates[mapping.capability] = candidate
        selection_limit = min(limit or self.max_selection, self.max_selection)
        return tuple(sorted(candidates.values(), key=self._sort_key)[:selection_limit])

    @staticmethod
    def _sort_key(candidate: ExpansionCandidate) -> tuple[float, str, str]:
        return (-candidate.priority, candidate.metric, candidate.capability)
