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
