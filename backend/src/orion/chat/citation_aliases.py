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


def citation_eligible_sources(
    messages: tuple[ContextMessage, ...],
    sources: tuple[SourceRef, ...],
) -> tuple[SourceRef, ...]:
    """Return canonical sources whose evidence remains model-visible.

    Canonical ToolResults may retain more SourceRefs than a compacted model projection
    retains evidence rows for. A source can be cited only when the projected tool
    message still carries evidence that can be correlated to that source.

    Internet search and Knowledge retrieval are row-addressable, so only retained
    result/segment rows are eligible. Other sourced ToolResults use their top-level
    source list when non-null data remains visible. The canonical timeline is never
    mutated.
    """

    if not sources:
        return ()

    sources_by_id = {source.source_ref_id: source for source in sources}
    internet_sources_by_url = {
        source.url: source.source_ref_id
        for source in sources
        if source.source_kind == "internet" and source.url
    }
    knowledge_sources_by_segment = {
        (source.document_id, source.segment_id): source.source_ref_id
        for source in sources
        if source.source_kind in {"session", "project"}
        and source.document_id is not None
        and source.segment_id is not None
    }
    eligible: set[str] = set()

    for message in messages:
        if message.role != "tool":
            continue
        try:
            payload = json.loads(message.content)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict) or payload.get("status") != "success":
            continue

        data = payload.get("data")
        if data is None:
            continue

        tool_name = payload.get("tool_name")
        if tool_name == "internet.search":
            if not isinstance(data, dict):
                continue
            results = data.get("results")
            if not isinstance(results, list):
                continue
            for result in results:
                if not isinstance(result, dict):
                    continue
                source_ref_id = result.get("source_ref_id")
                if isinstance(source_ref_id, str) and source_ref_id in sources_by_id:
                    eligible.add(source_ref_id)
                    continue
                url = result.get("url")
                if isinstance(url, str):
                    matched = internet_sources_by_url.get(url)
                    if matched is not None:
                        eligible.add(matched)
            continue

        if tool_name in {"knowledge.search", "knowledge.read"}:
            if not isinstance(data, dict):
                continue
            segments = data.get("segments")
            if not isinstance(segments, list):
                continue
            for segment in segments:
                if not isinstance(segment, dict):
                    continue
                document = segment.get("document")
                document_id = document.get("document_id") if isinstance(document, dict) else None
                segment_id = segment.get("segment_id")
                if isinstance(document_id, str) and isinstance(segment_id, str):
                    matched = knowledge_sources_by_segment.get((document_id, segment_id))
                    if matched is not None:
                        eligible.add(matched)
            continue

        model_sources = payload.get("sources")
        if not isinstance(model_sources, list):
            continue
        for source in model_sources:
            source_ref_id = source.get("source_ref_id") if isinstance(source, dict) else None
            if isinstance(source_ref_id, str) and source_ref_id in sources_by_id:
                eligible.add(source_ref_id)

    return tuple(source for source in sources if source.source_ref_id in eligible)


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
    Sources without a surviving evidence alias are omitted from the model-visible
    source envelope while remaining canonical in persistence. Arbitrary ToolResult.data
    is preserved verbatim except for the Internet runtime's own duplicated
    source-reference correlation fields.

    Persisted assistant citation markers are removed from model history because prior
    assistant prose is continuity, not evidence.
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

    # Internet row correlation still contains canonical IDs at this boundary, so
    # project it before pruning the top-level source envelope.
    _project_internet_data(payload, aliases)
    _project_source_list(payload.get("sources"), aliases)
    _project_provenance(payload.get("_orion_provenance"), aliases)

    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _project_source_list(value: Any, aliases: Mapping[str, str]) -> None:
    if not isinstance(value, list):
        return

    projected_sources: list[dict[str, Any]] = []
    for source in value:
        if not isinstance(source, dict):
            continue
        source_ref_id = source.get("source_ref_id")
        if not isinstance(source_ref_id, str):
            continue
        alias = aliases.get(source_ref_id)
        if alias is None:
            continue
        projected = dict(source)
        projected.pop("source_ref_id", None)
        projected["evidence_ref"] = alias
        projected_sources.append(projected)

    value[:] = projected_sources


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

    aliases_by_url: dict[str, str] = {}
    model_sources = payload.get("sources")
    if isinstance(model_sources, list):
        for source in model_sources:
            if not isinstance(source, dict):
                continue
            source_ref_id = source.get("source_ref_id")
            url = source.get("url")
            if isinstance(source_ref_id, str) and isinstance(url, str):
                alias = aliases.get(source_ref_id)
                if alias is not None:
                    aliases_by_url[url] = alias

    if tool_name == "internet.fetch":
        _project_internet_source_ref(data, aliases, aliases_by_url)
        return

    if tool_name != "internet.search":
        return
    results = data.get("results")
    if not isinstance(results, list):
        return
    for result in results:
        if isinstance(result, dict):
            _project_internet_source_ref(result, aliases, aliases_by_url)


def _project_internet_source_ref(
    value: dict[str, Any],
    aliases: Mapping[str, str],
    aliases_by_url: Mapping[str, str],
) -> None:
    source_ref_id = value.pop("source_ref_id", None)
    alias = aliases.get(source_ref_id) if isinstance(source_ref_id, str) else None
    if alias is None:
        url = value.get("url")
        if isinstance(url, str):
            alias = aliases_by_url.get(url)
    if alias is not None:
        value["evidence_ref"] = alias
