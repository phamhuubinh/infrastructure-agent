"""Resolve typed source constraints before capability dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.pipeline.request_semantics import SourceConstraint
from src.pipeline.semantic_plan import SemanticPlan
from src.pipeline.semantic_plan_validation import (
    SemanticPlanValidationReason,
    SemanticPlanValidationResult,
    SemanticPlanValidationValue,
)

if TYPE_CHECKING:
    from src.tool.knowledge_tool import KnowledgeTool


class SourceConstraintUnavailableError(ValueError):
    """A hard source constraint has no configured compatible source."""


@dataclass(frozen=True, slots=True)
class SemanticSourceValidationResult:
    """Exact source allow-set produced before capability selection."""

    validation: SemanticPlanValidationResult
    allowed_sources: frozenset[str] | None = None
    excluded_sources: frozenset[str] = frozenset()

    def validate_provenance(
        self,
        actual_sources: frozenset[str],
    ) -> SemanticPlanValidationResult:
        plan = self.validation.original_plan
        if plan is None:
            return SemanticPlanValidationResult.reject(
                SemanticPlanValidationReason.MALFORMED_PLAN
            )
        forbidden = actual_sources.intersection(self.excluded_sources)
        outside_allow_set = (
            actual_sources.difference(self.allowed_sources)
            if self.allowed_sources is not None
            else frozenset()
        )
        if forbidden or outside_allow_set:
            return SemanticPlanValidationResult.reject(
                SemanticPlanValidationReason.SOURCE_FORBIDDEN,
                plan=plan,
                values=(
                    SemanticPlanValidationValue.safe(
                        "source.provenance",
                        original=",".join(sorted(actual_sources)),
                        normalized=None,
                    ),
                ),
            )
        return SemanticPlanValidationResult.valid(plan)

    def to_trace_dict(self) -> dict[str, object]:
        trace = self.validation.to_trace_dict()
        trace["allowed_sources"] = (
            sorted(self.allowed_sources) if self.allowed_sources is not None else None
        )
        trace["excluded_sources"] = sorted(self.excluded_sources)
        return trace


_CONCRETE_SOURCES = frozenset(
    {
        SourceConstraint.LINUX,
        SourceConstraint.SSH,
        SourceConstraint.GRAFANA,
        SourceConstraint.ZABBIX,
        SourceConstraint.INTERNET,
        SourceConstraint.URL_ONLY,
    }
)


def allowed_source_names(
    knowledge_tool: KnowledgeTool,
    constraints: tuple[SourceConstraint, ...],
    *,
    target: str,
) -> frozenset[str] | None:
    """Return an exact allow-set, or ``None`` for an unconstrained request."""
    concrete = tuple(source for source in constraints if source in _CONCRETE_SOURCES)
    if not concrete:
        return None

    names = knowledge_tool.source_names()
    allowed: set[str] = set()
    for constraint in concrete:
        allowed.update(
            _names_for_constraint(
                knowledge_tool,
                constraint,
                target=target,
                names=names,
            )
        )

    if not allowed:
        label = ", ".join(source.name for source in concrete)
        raise SourceConstraintUnavailableError(
            f"Requested source constraint is unavailable: {label}."
        )
    return frozenset(allowed)


def validate_semantic_sources(
    knowledge_tool: KnowledgeTool,
    plan: SemanticPlan,
    *,
    target: str | None,
) -> SemanticSourceValidationResult:
    """Validate exact allow/exclude semantics without selecting a capability."""

    if not isinstance(plan, SemanticPlan):
        raise TypeError("plan must be a SemanticPlan.")
    allowed_constraints = plan.source_constraints
    excluded_constraints = plan.excluded_sources
    if any(not isinstance(item, SourceConstraint) for item in allowed_constraints):
        raise TypeError("source_constraints must contain SourceConstraint values.")
    if any(not isinstance(item, SourceConstraint) for item in excluded_constraints):
        raise TypeError("excluded_sources must contain SourceConstraint values.")

    uncertain = {SourceConstraint.UNSPECIFIED, SourceConstraint.UNKNOWN}
    if uncertain.intersection(allowed_constraints) or uncertain.intersection(
        excluded_constraints
    ):
        return SemanticSourceValidationResult(
            SemanticPlanValidationResult.clarify(
                plan,
                SemanticPlanValidationReason.PLANNER_UNCERTAIN,
            )
        )

    concrete_allowed = tuple(
        item for item in allowed_constraints if item in _CONCRETE_SOURCES
    )
    concrete_excluded = tuple(
        item for item in excluded_constraints if item in _CONCRETE_SOURCES
    )
    conflict = bool(set(concrete_allowed).intersection(concrete_excluded))
    conflict = conflict or (
        SourceConstraint.ANY in allowed_constraints and bool(concrete_allowed)
    )
    conflict = conflict or (
        SourceConstraint.NO_INTERNET in allowed_constraints
        and any(
            item in {SourceConstraint.INTERNET, SourceConstraint.URL_ONLY}
            for item in concrete_allowed
        )
    )
    if conflict:
        return SemanticSourceValidationResult(
            SemanticPlanValidationResult.reject(
                SemanticPlanValidationReason.SOURCE_CONFLICT,
                plan=plan,
            )
        )
    if SourceConstraint.URL_ONLY in allowed_constraints and plan.explicit_url is None:
        return SemanticSourceValidationResult(
            SemanticPlanValidationResult.clarify(
                plan,
                SemanticPlanValidationReason.PARAMETER_MISSING,
                values=(
                    SemanticPlanValidationValue.safe(
                        "parameter.url",
                        original=None,
                        normalized=None,
                    ),
                ),
            )
        )

    resolved_target = target or ""
    try:
        exact_allowed = allowed_source_names(
            knowledge_tool,
            allowed_constraints,
            target=resolved_target,
        )
    except SourceConstraintUnavailableError:
        return SemanticSourceValidationResult(
            SemanticPlanValidationResult.unavailable(
                plan,
                SemanticPlanValidationReason.SOURCE_UNAVAILABLE,
                values=(
                    SemanticPlanValidationValue.safe(
                        "source.allowed",
                        original=",".join(item.name for item in concrete_allowed),
                        normalized=None,
                    ),
                ),
            )
        )

    needs_configured_names = bool(concrete_excluded) or (
        SourceConstraint.NO_INTERNET in allowed_constraints
    )
    configured_names = (
        tuple(knowledge_tool.source_names()) if needs_configured_names else ()
    )
    excluded_names: set[str] = set()
    for constraint in concrete_excluded:
        excluded_names.update(
            _names_for_constraint(
                knowledge_tool,
                constraint,
                target=resolved_target,
                names=configured_names,
            )
        )
    if SourceConstraint.NO_INTERNET in allowed_constraints:
        excluded_names.update(
            _names_for_constraint(
                knowledge_tool,
                SourceConstraint.INTERNET,
                target=resolved_target,
                names=configured_names,
            )
        )

    if exact_allowed is None and excluded_names:
        exact_allowed = frozenset(set(configured_names) - excluded_names)
    elif exact_allowed is not None:
        exact_allowed = frozenset(set(exact_allowed) - excluded_names)
    if exact_allowed is not None and not exact_allowed:
        return SemanticSourceValidationResult(
            SemanticPlanValidationResult.unavailable(
                plan,
                SemanticPlanValidationReason.SOURCE_UNAVAILABLE,
            ),
            excluded_sources=frozenset(excluded_names),
        )

    values: list[SemanticPlanValidationValue] = []
    if exact_allowed is not None:
        values.append(
            SemanticPlanValidationValue.safe(
                "source.allowed",
                original=",".join(item.name for item in allowed_constraints),
                normalized=",".join(sorted(exact_allowed)),
            )
        )
    if excluded_names:
        values.append(
            SemanticPlanValidationValue.safe(
                "source.excluded",
                original=",".join(item.name for item in excluded_constraints),
                normalized=",".join(sorted(excluded_names)),
            )
        )
    return SemanticSourceValidationResult(
        SemanticPlanValidationResult.valid(plan, values=tuple(values)),
        allowed_sources=exact_allowed,
        excluded_sources=frozenset(excluded_names),
    )


def _names_for_constraint(
    knowledge_tool: KnowledgeTool,
    constraint: SourceConstraint,
    *,
    target: str,
    names: tuple[str, ...] | list[str],
) -> set[str]:
    if constraint is SourceConstraint.SSH:
        return {
            target if target in names and knowledge_tool.is_ssh_target(target) else ""
        } - {""}
    source_kind = {
        SourceConstraint.LINUX: "linux",
        SourceConstraint.GRAFANA: "grafana",
        SourceConstraint.ZABBIX: "zabbix",
        SourceConstraint.INTERNET: "internet",
        SourceConstraint.URL_ONLY: "internet",
    }.get(constraint)
    if source_kind is None:
        return set()
    return {name for name in names if knowledge_tool.source_kind(name) == source_kind}


_SOURCE_KIND_BY_CONSTRAINT = {
    SourceConstraint.LINUX: "linux",
    SourceConstraint.SSH: "ssh",
    SourceConstraint.GRAFANA: "grafana",
    SourceConstraint.ZABBIX: "zabbix",
    SourceConstraint.INTERNET: "internet",
    SourceConstraint.URL_ONLY: "internet",
}


def compute_comparison_status(
    constraints: tuple[SourceConstraint, ...],
    fact_sources: frozenset[str],
) -> str | None:
    """GA2-E04: derive COMPLETE/PARTIAL/UNAVAILABLE for a multi-source
    comparison request ("So sánh CPU từ Grafana và Zabbix trên monitor.").

    Returns ``None`` when the request does not name two or more distinct
    *concrete* sources — i.e. it is not a comparison request at all, and no
    comparison status applies. Never conflates "some evidence was
    collected" with "every requested source was actually represented": a
    request naming Grafana and Zabbix that only produced Grafana facts
    (e.g. Zabbix was unreachable) must be flagged PARTIAL with the missing
    source explicit, never silently reported as if it were complete.
    """
    concrete = tuple(
        dict.fromkeys(
            constraint
            for constraint in constraints
            if constraint in _CONCRETE_SOURCES
        )
    )
    if len(concrete) < 2:
        return None
    represented = {
        constraint
        for constraint in concrete
        if _SOURCE_KIND_BY_CONSTRAINT[constraint] in fact_sources
    }
    if not represented:
        return "UNAVAILABLE"
    if len(represented) < len(concrete):
        return "PARTIAL"
    return "COMPLETE"


def missing_comparison_sources(
    constraints: tuple[SourceConstraint, ...],
    fact_sources: frozenset[str],
) -> tuple[SourceConstraint, ...]:
    """GA2-E04: which of the requested comparison sources produced no
    facts at all, for an explicit "missing X" note in the response."""
    return tuple(
        constraint
        for constraint in dict.fromkeys(constraints)
        if constraint in _CONCRETE_SOURCES
        and _SOURCE_KIND_BY_CONSTRAINT[constraint] not in fact_sources
    )
