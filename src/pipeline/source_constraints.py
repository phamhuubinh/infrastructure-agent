"""Resolve typed source constraints before capability dispatch."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.pipeline.request_semantics import SourceConstraint

if TYPE_CHECKING:
    from src.tool.knowledge_tool import KnowledgeTool


class SourceConstraintUnavailableError(ValueError):
    """A hard source constraint has no configured compatible source."""


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
        if constraint is SourceConstraint.SSH:
            if target in names and knowledge_tool.is_ssh_target(target):
                allowed.add(target)
            continue
        source_kind = {
            SourceConstraint.LINUX: "linux",
            SourceConstraint.GRAFANA: "grafana",
            SourceConstraint.ZABBIX: "zabbix",
            SourceConstraint.INTERNET: "internet",
            SourceConstraint.URL_ONLY: "internet",
        }[constraint]
        allowed.update(
            name for name in names if knowledge_tool.source_kind(name) == source_kind
        )

    if not allowed:
        label = ", ".join(source.name for source in concrete)
        raise SourceConstraintUnavailableError(
            f"Requested source constraint is unavailable: {label}."
        )
    return frozenset(allowed)


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
