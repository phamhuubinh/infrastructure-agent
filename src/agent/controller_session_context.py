"""Bounded session-context bridge for the isolated Agent v2 controller loop."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import replace
from enum import Enum

from src.agent.conversation_store import ConversationStoreProtocol
from src.agent.semantic_session_context_selector import SemanticSessionContextSelector
from src.agent.session_investigation_context import (
    SessionContextResolver,
    SessionInvestigationContext,
)
from src.model.protocol.controller_prompt import ControllerPromptContext
from src.pipeline.agent_action_validator import (
    AgentActionValidationReason,
    AgentActionValidationResult,
)
from src.pipeline.hard_request_constraints import (
    HardRequestConstraints,
    HardTargetReference,
)
from src.pipeline.target_resolver import TargetResolver


class ContextManagementStatus(str, Enum):
    RESET = "reset"
    UPDATED = "updated"
    UNKNOWN_TARGET = "unknown_target"


_FUTURE_SCOPE = re.compile(
    r"(?:cho\s+các\s+câu\s+tiếp\s+theo|từ\s+giờ|for\s+the\s+next\s+questions|from\s+now\s+on)",
    re.IGNORECASE,
)
_POSITIVE_TARGET = re.compile(
    r"(?:chỉ\s+dùng|use\s+only|switch\s+to)\s+([A-Za-z0-9_.:-]+)",
    re.IGNORECASE,
)


class ControllerSessionContext:
    """One-run snapshot, authority adapter, and validated future-state writer."""

    def __init__(
        self,
        session_store: ConversationStoreProtocol,
        *,
        target_resolver: TargetResolver,
        selector: SemanticSessionContextSelector | None = None,
    ) -> None:
        if not isinstance(target_resolver, TargetResolver):
            raise TypeError("target_resolver must be TargetResolver.")
        context = session_store.investigation_context
        if not isinstance(context, SessionInvestigationContext):
            raise TypeError(
                "session_store investigation_context must be SessionInvestigationContext."
            )
        self._store = session_store
        self._target_resolver = target_resolver
        self._selector = selector or SemanticSessionContextSelector()
        self._stored_context = context
        self._selected_context: ControllerPromptContext | None = None
        self._used_target: str | None = None
        self._used_sources: tuple = ()
        self._used_excluded_sources: tuple = ()

    def select(
        self, raw_request: str, current: HardRequestConstraints
    ) -> ControllerPromptContext | None:
        """Read once and select the frozen, allowlisted prompt snapshot."""

        if not isinstance(current, HardRequestConstraints):
            raise TypeError("current must be HardRequestConstraints.")
        selection = self._selector.select(raw_request, self._stored_context)
        selected = selection.context
        if selected is None:
            self._selected_context = None
            return None
        self._selected_context = ControllerPromptContext(
            target=None if current.explicit_target is not None else selected.target,
            concept=selected.concept,
            service=selected.service,
            path=selected.path,
            time_range=selected.time_range,
            sources=() if _has_explicit_source_policy(current) else selected.sources,
            excluded_sources=(
                ()
                if _has_explicit_source_policy(current)
                else selected.excluded_sources
            ),
            pending_clarification_field=selected.pending_clarification_field,
        )
        return self._selected_context

    def manage(
        self, raw_request: str, hard_constraints: HardRequestConstraints
    ) -> ContextManagementStatus | None:
        """Apply exact reset/preference directives without model or execution work."""

        if SessionContextResolver.is_reset_request(raw_request):
            self._persist(self._stored_context.reset())
            return ContextManagementStatus.RESET
        if not _FUTURE_SCOPE.search(raw_request):
            return None
        match = _POSITIVE_TARGET.search(raw_request)
        if match is None:
            return None
        canonical_target = self._target_resolver.resolve_exact_target_reference(
            match.group(1)
        )
        if canonical_target is None:
            return ContextManagementStatus.UNKNOWN_TARGET
        updated = self._stored_context.switch_target(canonical_target)
        if _has_explicit_source_policy(hard_constraints):
            updated = replace(
                updated,
                active_sources=hard_constraints.source_constraints,
                active_excluded_sources=hard_constraints.excluded_sources,
            )
        self._persist(updated)
        return ContextManagementStatus.UPDATED

    def discovery_constraints(
        self, current: HardRequestConstraints
    ) -> HardRequestConstraints:
        return self._with_inherited_sources(current)

    def action_constraints(
        self,
        current: HardRequestConstraints,
        selected_schema: Mapping[str, object] | None,
    ) -> HardRequestConstraints:
        effective = self._with_inherited_sources(current)
        if (
            current.explicit_target is None
            and self._selected_context is not None
            and self._selected_context.target is not None
            and _schema_target_kind(selected_schema) == "machine"
        ):
            target = self._selected_context.target
            effective = replace(
                effective,
                explicit_target=HardTargetReference(target, target),
            )
        return effective

    def record_validation(
        self,
        validation: AgentActionValidationResult,
        current: HardRequestConstraints,
        effective: HardRequestConstraints,
    ) -> None:
        """Persist only validated authority, never a decision or observation."""

        if validation.valid:
            updated = self._stored_context
            if validation.target_id is not None:
                if validation.target_id != updated.active_target:
                    updated = updated.switch_target(validation.target_id)
                elif updated.pending_clarification_field == "target":
                    updated = updated.with_pending_clarification(None)
                if (
                    current.explicit_target is None
                    and effective.explicit_target is not None
                ):
                    self._used_target = validation.target_id
            if _has_explicit_source_policy(current):
                updated = replace(
                    updated,
                    active_sources=current.source_constraints,
                    active_excluded_sources=current.excluded_sources,
                )
            elif _uses_inherited_source_authority(validation, effective):
                self._used_sources = effective.source_constraints
                self._used_excluded_sources = effective.excluded_sources
            self._persist(updated)
            return
        if validation.reason in {
            AgentActionValidationReason.TARGET_REQUIRED,
            AgentActionValidationReason.TARGET_UNKNOWN,
        }:
            self._persist(self._stored_context.with_pending_clarification("target"))

    def completion_constraints(
        self, current: HardRequestConstraints
    ) -> HardRequestConstraints:
        """Apply inherited authority only after this run used it successfully."""

        result = current
        if current.explicit_target is None and self._used_target is not None:
            result = replace(
                result,
                explicit_target=HardTargetReference(
                    self._used_target, self._used_target
                ),
            )
        if not _has_explicit_source_policy(current) and (
            self._used_sources or self._used_excluded_sources
        ):
            result = replace(
                result,
                source_constraints=self._used_sources,
                excluded_sources=self._used_excluded_sources,
            )
        return result

    def _with_inherited_sources(
        self, current: HardRequestConstraints
    ) -> HardRequestConstraints:
        if (
            _has_explicit_source_policy(current)
            or self._selected_context is None
            or not (
                self._selected_context.sources
                or self._selected_context.excluded_sources
            )
        ):
            return current
        return replace(
            current,
            source_constraints=self._selected_context.sources,
            excluded_sources=self._selected_context.excluded_sources,
        )

    def _persist(self, context: SessionInvestigationContext) -> None:
        self._stored_context = context
        self._store.set_investigation_context(context)


def _has_explicit_source_policy(constraints: HardRequestConstraints) -> bool:
    return bool(constraints.source_constraints or constraints.excluded_sources)


def _uses_inherited_source_authority(
    validation: AgentActionValidationResult,
    effective: HardRequestConstraints,
) -> bool:
    return _has_explicit_source_policy(effective) and validation.source_family in {
        "linux",
        "grafana",
        "zabbix",
        "internet",
    }


def _schema_target_kind(schema: Mapping[str, object] | None) -> str | None:
    if not isinstance(schema, Mapping):
        return None
    requirements = schema.get("target_requirements")
    if not isinstance(requirements, Mapping):
        return None
    kind = requirements.get("kind")
    return kind if isinstance(kind, str) else None


__all__ = ["ContextManagementStatus", "ControllerSessionContext"]
