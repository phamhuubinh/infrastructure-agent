"""Request-local model-visible aliases for canonical citation source identities."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from orion.contracts import (
    ContextMessage,
    ModelTurn,
    SourceRef,
    replace_source_citation_ref_ids,
    strip_source_citation_markers,
)


@dataclass(frozen=True)
class CitationAlias:
    """One request-local model alias mapped to Orion's canonical source identity."""

    alias: str
    source_ref_id: str


def build_citation_aliases(sources: tuple[SourceRef, ...]) -> tuple[CitationAlias, ...]:
    """Assign dense S1..Sn aliases in first-visible-source order."""

    aliases: list[CitationAlias] = []
    seen: set[str] = set()
    for source in sources:
        if source.source_ref_id in seen:
            continue
        seen.add(source.source_ref_id)
        aliases.append(
            CitationAlias(alias=f"S{len(aliases) + 1}", source_ref_id=source.source_ref_id)
        )
    return tuple(aliases)


def model_visible_citation_messages(
    messages: tuple[ContextMessage, ...],
    aliases: tuple[CitationAlias, ...],
) -> tuple[ContextMessage, ...]:
    """Hide canonical citation IDs at the model boundary.

    Orion-owned source/provenance fields are projected to request-local aliases.
    Arbitrary ToolResult.data is preserved verbatim except for the Internet
    runtime's own duplicated source-reference correlation fields.
    Persisted assistant citation markers are removed from model history because
    prior assistant prose is continuity, not evidence.
    """

    by_source_ref_id = {item.source_ref_id: item.alias for item in aliases}
    projected: list[ContextMessage] = []
    for message in messages:
        if message.role == "assistant":
            projected.append(
                message.model_copy(
                    update={
                        "content": strip_source_citation_markers(message.content),
                        "citation_source_ref_ids": (),
                    }
                )
            )
            continue
        if message.role == "tool":
            projected.append(
                message.model_copy(
                    update={
                        "content": _project_tool_content(message.content, by_source_ref_id),
                    }
                )
            )
            continue
        projected.append(message)
    return tuple(projected)


def resolve_model_citation_aliases(
    turn: ModelTurn,
    aliases: tuple[CitationAlias, ...],
) -> ModelTurn:
    """Resolve provider-parsed evidence aliases to canonical IDs before validation.

    Unknown aliases deliberately remain unresolved so terminal citation validation
    can reject them and use the existing single correction path.
    """

    assistant = turn.assistant
    if assistant is None or not assistant.citation_evidence_refs:
        return turn
    by_alias = {item.alias: item.source_ref_id for item in aliases}
    if any(reference not in by_alias for reference in assistant.citation_evidence_refs):
        return turn
    canonical = tuple(by_alias[reference] for reference in assistant.citation_evidence_refs)
    replacements = {
        reference: by_alias[reference] for reference in assistant.citation_evidence_refs
    }
    resolved = assistant.model_copy(
        update={
            "content": replace_source_citation_ref_ids(assistant.content, replacements),
            "citation_source_ref_ids": canonical,
            "citation_evidence_refs": (),
        }
    )
    return turn.model_copy(update={"assistant": resolved})


def _project_tool_content(content: str, aliases: Mapping[str, str]) -> str:
    payload = json.loads(content)
    if not isinstance(payload, dict):
        return content

    _project_source_list(payload.get("sources"), aliases)
    _project_provenance(payload.get("_orion_provenance"), aliases)
    _project_internet_data(payload, aliases)

    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _project_source_list(value: Any, aliases: Mapping[str, str]) -> None:
    if not isinstance(value, list):
        return
    for source in value:
        if not isinstance(source, dict):
            continue
        source_ref_id = source.pop("source_ref_id", None)
        if isinstance(source_ref_id, str):
            alias = aliases.get(source_ref_id)
            if alias is not None:
                source["evidence_ref"] = alias


def _project_provenance(value: Any, aliases: Mapping[str, str]) -> None:
    if not isinstance(value, dict):
        return
    source_refs = value.pop("source_refs", None)
    if not isinstance(source_refs, list):
        return
    value["evidence_refs"] = [
        aliases[source_ref_id]
        for source_ref_id in source_refs
        if isinstance(source_ref_id, str) and source_ref_id in aliases
    ]


def _project_internet_data(payload: dict[str, Any], aliases: Mapping[str, str]) -> None:
    tool_name = payload.get("tool_name")
    data = payload.get("data")
    if not isinstance(data, dict):
        return

    if tool_name == "internet.fetch":
        _project_internet_source_ref(data, aliases)
        return

    if tool_name != "internet.search":
        return
    results = data.get("results")
    if not isinstance(results, list):
        return
    for result in results:
        if isinstance(result, dict):
            _project_internet_source_ref(result, aliases)


def _project_internet_source_ref(value: dict[str, Any], aliases: Mapping[str, str]) -> None:
    source_ref_id = value.pop("source_ref_id", None)
    if not isinstance(source_ref_id, str):
        return
    alias = aliases.get(source_ref_id)
    if alias is not None:
        value["evidence_ref"] = alias
