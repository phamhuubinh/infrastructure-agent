"""Bounded session-state selection for the semantic planner prompt."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from src.agent.session_investigation_context import (
    SessionContextResolver,
    SessionInvestigationContext,
)
from src.model.protocol.semantic_planner_prompt import PlannerPromptContext
from src.pipeline.request_semantics import SourceConstraint


class SessionContextSelectionStatus(str, Enum):
    """Whether stale planner context should be inherited or cleared."""

    EMPTY = "empty"
    INHERIT = "inherit"
    CLEAR = "clear"


@dataclass(frozen=True, slots=True)
class SessionContextSelection:
    status: SessionContextSelectionStatus
    context: PlannerPromptContext | None = None
    inherited_fields: tuple[str, ...] = ()


class SemanticSessionContextSelector:
    """Select only prior semantics needed to interpret one new request.

    Raw evidence, previous answers, evidence receipts, incident history and
    response formatting preferences are intentionally unreachable here.
    """

    _CONCEPT = re.compile(
        r"\b(?:cpu|ram|memory|disk|storage|network|service|process|log|swap)\b",
        re.IGNORECASE,
    )
    _RESOURCE_REFERENCE = re.compile(
        r"\b(?:same|that|it|nó|no|đó|do|kia|service|dịch vụ|dich vu|path|"
        r"đường dẫn|duong dan)\b",
        re.IGNORECASE,
    )
    _VALID_PRIOR_SOURCES = frozenset(
        {
            SourceConstraint.LINUX,
            SourceConstraint.SSH,
            SourceConstraint.GRAFANA,
            SourceConstraint.ZABBIX,
            SourceConstraint.INTERNET,
            SourceConstraint.URL_ONLY,
            SourceConstraint.NO_INTERNET,
        }
    )

    def select(
        self,
        raw_request: str,
        context: SessionInvestigationContext,
    ) -> SessionContextSelection:
        if not isinstance(raw_request, str) or not raw_request.strip():
            raise ValueError("Session-context selection requires non-empty text.")
        if not isinstance(context, SessionInvestigationContext):
            raise TypeError("context must be SessionInvestigationContext.")
        if context == SessionInvestigationContext():
            return SessionContextSelection(SessionContextSelectionStatus.EMPTY)

        pending_answer = (
            context.pending_clarification_field is not None
            and len(raw_request.split()) <= 6
        )
        is_follow_up = SessionContextResolver.is_follow_up_request(raw_request)
        if not (pending_answer or is_follow_up):
            # A standalone request starts with no prior planner semantics.  The
            # caller may persist a new context only after that request succeeds.
            return SessionContextSelection(SessionContextSelectionStatus.CLEAR)

        # A short answer to a target clarification replaces the old target;
        # carrying it forward would bias the planner toward stale state.
        target = (
            context.active_target
            if context.pending_clarification_field != "target"
            else None
        )
        concept = None if self._CONCEPT.search(raw_request) else context.active_concept
        references_resource = bool(self._RESOURCE_REFERENCE.search(raw_request))
        service = context.active_service if references_resource else None
        path = context.active_path if references_resource else None
        time_range = (
            context.active_time_range.source_phrase
            if context.active_time_range is not None
            else None
        )

        sources = tuple(
            source
            for source in context.active_sources
            if source in self._VALID_PRIOR_SOURCES
        )
        excluded = tuple(
            source
            for source in context.active_excluded_sources
            if source in self._VALID_PRIOR_SOURCES
        )
        pending_field = context.pending_clarification_field
        selected: tuple[tuple[str, object], ...] = (
            ("target", target),
            ("concept", concept),
            ("service", service),
            ("path", path),
            ("time_range", time_range),
            ("sources", sources),
            ("excluded_sources", excluded),
            ("pending_clarification_field", pending_field),
        )
        inherited = tuple(
            name for name, value in selected if value not in (None, (), "")
        )
        planner_context = PlannerPromptContext(
            target=target,
            concept=concept,
            service=service,
            path=path,
            time_range=time_range,
            sources=sources,
            excluded_sources=excluded,
            pending_clarification_field=pending_field,
        )
        if not inherited:
            return SessionContextSelection(SessionContextSelectionStatus.EMPTY)
        return SessionContextSelection(
            status=SessionContextSelectionStatus.INHERIT,
            context=planner_context,
            inherited_fields=inherited,
        )


__all__ = [
    "SemanticSessionContextSelector",
    "SessionContextSelection",
    "SessionContextSelectionStatus",
]
