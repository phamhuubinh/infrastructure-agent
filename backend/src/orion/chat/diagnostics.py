"""Bounded, provider-neutral diagnostics for model and tool phases.

The runtime owns when these records are made.  This module only provides an
optional sink; it deliberately knows nothing about the QA runner or provider
request formats.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Protocol

from orion.security import redact_public

MODEL_INPUT_TEXT_LIMIT = 12_000
CANONICAL_RESULT_LIMIT = 12_000
MAX_RECORDS_PER_REQUEST = 160


class RuntimeDiagnosticSink(Protocol):
    """Best-effort receiver for runtime diagnostic records."""

    def record(self, record: Mapping[str, object]) -> None: ...


class BoundedModelInputDiagnostics:
    """QA-oriented in-memory sink with explicit content bounds.

    It is injected only by an opt-in composition.  The output intentionally
    excludes provider payloads, prompts, request headers, and reasoning.
    """

    def __init__(
        self,
        *,
        text_limit: int = MODEL_INPUT_TEXT_LIMIT,
        canonical_result_limit: int = CANONICAL_RESULT_LIMIT,
        records_limit: int = MAX_RECORDS_PER_REQUEST,
    ) -> None:
        self._text_limit = text_limit
        self._canonical_result_limit = canonical_result_limit
        self._records_limit = records_limit
        self._records: dict[str, list[dict[str, object]]] = defaultdict(list)
        self._omitted_records: dict[str, int] = defaultdict(int)

    def record(self, record: Mapping[str, object]) -> None:
        request_id = record.get("request_id")
        if not isinstance(request_id, str):
            return
        records = self._records[request_id]
        if len(records) >= self._records_limit:
            self._omitted_records[request_id] += 1
            return
        records.append(self._safe_record(record))

    def records(self, request_id: str) -> dict[str, object]:
        records = self._records.get(request_id, [])
        return {
            "diagnostic_schema_version": 1,
            "records": list(records),
            "records_truncated": self._omitted_records.get(request_id, 0) > 0,
            "omitted_record_count": self._omitted_records.get(request_id, 0),
        }

    def _safe_record(self, record: Mapping[str, object]) -> dict[str, object]:
        safe = redact_public(dict(record))
        assert isinstance(safe, dict)
        model_input = safe.get("model_input")
        if isinstance(model_input, dict):
            safe["model_input"] = self._safe_model_input(model_input)
        canonical_result = safe.get("canonical_result")
        if canonical_result is not None:
            value, truncated, bytes_before = _bounded_value(
                canonical_result, self._canonical_result_limit
            )
            safe["canonical_result"] = value
            safe["canonical_result_truncated"] = truncated
            safe["canonical_result_bytes"] = bytes_before
        return safe

    def _safe_model_input(self, model_input: dict[str, object]) -> dict[str, object]:
        safe = dict(model_input)
        projections = safe.get("tool_result_projections")
        if not isinstance(projections, list):
            return safe
        captured: list[dict[str, object]] = []
        for projection in projections:
            if not isinstance(projection, dict):
                continue
            item = dict(projection)
            content = item.get("content")
            if isinstance(content, str):
                bounded, truncated, bytes_before = _bounded_text(content, self._text_limit)
                item["content"] = bounded
                item["content_truncated"] = truncated
                item["content_bytes"] = bytes_before
            captured.append(item)
        safe["tool_result_projections"] = captured
        return safe


def model_input_snapshot(
    messages: Sequence[object],
    exposed_tool_names: Sequence[str],
    visible_source_ids: Sequence[str],
    request_bytes: int,
) -> dict[str, object]:
    """Describe only the data-bearing tool inputs sent to the model.

    ``messages`` is intentionally duck-typed so this diagnostic module does
    not become part of the core context contract.
    """
    projections: list[dict[str, object]] = []
    for message in messages:
        if getattr(message, "role", None) != "tool":
            continue
        content = getattr(message, "content", "")
        if not isinstance(content, str):
            continue
        item: dict[str, object] = {
            "tool_call_id": getattr(message, "tool_call_id", None),
            "tool_name": getattr(message, "tool_name", None),
            "content": content,
            "projection_omissions": _projection_omissions(content),
        }
        projections.append(item)
    return {
        "request_proxy_bytes": request_bytes,
        "exposed_tool_names": list(exposed_tool_names),
        "visible_source_ref_ids": list(visible_source_ids),
        "tool_result_projections": projections,
    }


def _projection_omissions(content: str) -> list[object]:
    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        return []
    if not isinstance(value, dict):
        return []
    projection = value.get("_orion_projection")
    if not isinstance(projection, dict):
        return []
    omissions = projection.get("omissions")
    return list(omissions) if isinstance(omissions, list) else []


def _bounded_text(value: str, limit: int) -> tuple[str, bool, int]:
    byte_count = len(value.encode("utf-8"))
    if byte_count <= limit:
        return value, False, byte_count
    encoded = value.encode("utf-8")[:limit]
    return encoded.decode("utf-8", errors="ignore"), True, byte_count


def _bounded_value(value: object, limit: int) -> tuple[object, bool, int]:
    serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    byte_count = len(serialized.encode("utf-8"))
    if byte_count <= limit:
        return value, False, byte_count
    bounded, _, _ = _bounded_text(serialized, limit)
    return bounded, True, byte_count
