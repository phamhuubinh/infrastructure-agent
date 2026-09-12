"""Bounded, structure-preserving projections for model-visible tool data."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from orion.contracts import ToolResult

_MAX_OMISSION_RECORDS = 12
_PRIORITY_KEYS = {
    "target_ref",
    "status",
    "changed",
    "verification",
    "outcome_unknown",
    "path",
    "cursor",
    "next_cursor",
    "complete",
    "count",
    "total",
    "result_count",
    "returned_count",
    "segment_count",
    "total_segments",
    "zero_matches_in_query",
    "absence_of_events_established",
    "possibly_truncated",
    "result_completeness",
    "evidence_scope",
    "time_coverage",
}
_EVIDENCE_METADATA_KEYS = ("evidence_scope", "time_coverage")


def compact_json(value: object) -> str:
    """Serialize deterministic model data without insignificant JSON whitespace."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def project_tool_result(result: ToolResult, maximum_bytes: int) -> str:
    """Fit data AND actual omission metadata; never modify the canonical result.

    Reduction follows a budget-independent order: lower-priority dict fields,
    list tails, then detail within the first remaining item. A fitting prefix is
    selected using actual serialized costs, without a speculative byte reserve.
    This nested sequence cannot trade away included items as the cap increases.

    Status/error/correlation/sources are immutable. Only their envelope plus the
    minimal truthful omission summary may exceed the cap (the irreducible case).
    Per-path records are bounded; unreported_list_items sums cardinalities of
    unreported list records, including nested lists, NOT distinct observations.
    essential_metadata contains only upstream-provided fields; {} means neither
    coverage field was supplied, not that coverage is complete.
    source_data_state is an irreducible projection-level fact: it distinguishes
    upstream nonempty evidence from an empty successful result even when all
    data rows and coverage metadata are omitted.
    """
    canonical = result.model_dump(mode="json")
    if canonical["read_progress"] is None:
        del canonical["read_progress"]
    serialized = compact_json(canonical)
    original_bytes = len(serialized.encode("utf-8"))
    if original_bytes <= maximum_bytes:
        return serialized

    original = canonical["data"]
    envelope = {key: value for key, value in canonical.items() if key != "data"}
    projected = original
    encoded = ""

    def assign(value: Any) -> None:
        nonlocal projected
        projected = value

    def fits() -> bool:
        nonlocal encoded
        # A data-only lower bound is safe; omission costs are NOT monotonic.
        # Skip omission collection/serialization when data alone cannot fit.
        if (
            projected not in (None, [], {})
            and len(compact_json(projected).encode()) > maximum_bytes
        ):
            return False
        omissions: list[dict[str, Any]] = []
        _collect_omissions(original, projected, "$.data", omissions)
        metadata: dict[str, Any] = {
            "applied": True,
            "data_state": _data_state(original, projected),
            "source_data_state": _source_data_state(result.status, original, projected),
            "essential_metadata": _essential_metadata_states(original, projected),
            "original_bytes": original_bytes,
            "maximum_bytes": maximum_bytes,
        }
        # Spend only the actual needed metadata bytes. Retain the longest fitting
        # record prefix, with explicit counts for every unreported list record.
        retained_count = min(len(omissions), _MAX_OMISSION_RECORDS)
        count_keys = ("original_items", "included_items", "omitted_items")
        unreported = {
            key: sum(item[key] for item in omissions[retained_count:] if key in item)
            for key in count_keys
        }
        unreported_lists = sum("original_items" in item for item in omissions[retained_count:])
        for retained in range(retained_count, -1, -1):
            metadata["omissions"] = omissions[:retained]
            metadata["omission_entries_omitted"] = len(omissions) - retained
            if unreported_lists:
                metadata["unreported_list_items"] = unreported
            else:
                metadata.pop("unreported_list_items", None)
            encoded = compact_json({**envelope, "data": projected, "_orion_projection": metadata})
            if len(encoded.encode("utf-8")) <= maximum_bytes:
                return True
            if retained and "original_items" in omissions[retained - 1]:
                unreported_lists += 1
                for key in count_keys:
                    unreported[key] += omissions[retained - 1][key]
        return False

    # The unchanged canonical already failed, so adding metadata cannot fit it.
    if _shrink(original, assign, fits, maximum_bytes):
        return encoded
    # No data-bearing candidate fits. Keep true empty upstream containers intact;
    # nonempty-but-unavailable data is null, never a misleading [] or {}.
    assign(original if _data_state(original, None) == "upstream_empty" else None)
    fits()
    return encoded


def _shrink(
    value: Any, assign: Callable[[Any], None], fits: Callable[[], bool], maximum_bytes: int
) -> bool:
    """Search a fixed decreasing evidence sequence, using exact envelope costs.

    List prefixes are exhaustive, longest first: including nested data can REMOVE
    omission records, so final serialized cost cannot be binary-searched. Only
    the data-only prefix cost is monotonic and safely excludes oversized prefixes.
    With cap B, at most (B - 1) // 2 nonempty prefixes reach fits (each JSON item
    costs at least one byte plus a comma). Thus candidate serialization is bounded
    by the context cap, not an O(N**2) sequence of full N-item serializations.
    """
    if isinstance(value, list) and value:
        prefix_bytes = 2
        largest = 0
        for index in range(len(value) - 1):
            item = value[index]
            prefix_bytes += len(compact_json(item).encode()) + (1 if index else 0)
            if prefix_bytes > maximum_bytes:
                break
            largest = index + 1
        for included in range(largest, 0, -1):
            assign(value[:included])
            if fits():
                return True
        assign(value[:1])
        if _shrink(
            value[0], lambda item: assign([item] if item is not None else None), fits, maximum_bytes
        ):
            return True
    elif isinstance(value, dict) and value:
        current = dict(value)
        assign(current)
        positions = {key: index for index, key in enumerate(value)}
        keys = sorted(
            value,
            key=lambda key: (
                key not in _EVIDENCE_METADATA_KEYS,
                key not in _PRIORITY_KEYS,
                positions[key],
            ),
        )
        for key in reversed(keys):

            def assign_child(item: Any, child_key: str = key) -> None:
                if item is None:
                    current.pop(child_key, None)
                else:
                    current[child_key] = item
                assign(current if current else None)

            if _shrink(value[key], assign_child, fits, maximum_bytes):
                return True
            assign_child(None)
            if fits():
                return True
    elif isinstance(value, str) and value:
        # Unlike lists, strictly partial string prefixes have monotonic cost for
        # EACH fixed record-retention count: each character adds >=1 UTF-8/JSON
        # byte, and omitted_characters loses at most one decimal digit. Omission
        # paths/counts and all coverage states stay fixed. The union of these
        # feasible prefix intervals is still an interval, so binary search is safe.
        # Exclude an ellipsis replacement equal to the full original: completing
        # that value removes metadata (and the full value already failed above).
        low = 1
        high = min(len(value) - (2 if value.endswith("…") else 1), maximum_bytes)
        best = 0
        while low <= high:
            middle = (low + high) // 2
            assign(value[:middle] + "…")
            if fits():
                best, low = middle, middle + 1
            else:
                high = middle - 1
        if best:
            assign(value[:best] + "…")
            return fits()
    assign(None)
    return fits()


def _data_state(original: Any, projected: Any) -> str:
    if original is None or original == {} or original == []:
        return "upstream_empty"
    if projected is None:
        return "omitted"
    return "complete" if projected == original else "partial"


def _source_data_state(status: str, original: Any, projected: Any) -> str:
    """Name source-data presence without relying on a null projected value."""
    if original is None or original == {} or original == []:
        return "upstream_empty" if status == "success" else "unavailable"
    return "upstream_nonempty_omitted" if projected is None else "upstream_nonempty_partial"


def _essential_metadata_states(original: Any, projected: Any) -> dict[str, str]:
    return {
        key: (
            "omitted"
            if not isinstance(projected, dict) or key not in projected
            else "complete"
            if projected[key] == original[key]
            else "partial"
        )
        for key in _EVIDENCE_METADATA_KEYS
        if isinstance(original, dict) and key in original
    }


def _collect_omissions(
    original: Any, projected: Any, path: str, omissions: list[dict[str, Any]]
) -> None:
    if original == projected:
        return
    if isinstance(original, list):
        included = len(projected) if isinstance(projected, list) else 0
        omissions.append(
            {
                "path": path,
                "original_items": len(original),
                "included_items": included,
                "omitted_items": len(original) - included,
            }
        )
        for index, item in enumerate(original):
            if index < included:
                _collect_omissions(item, projected[index], f"{path}[{index}]", omissions)
            else:
                _collect_nested_lists(item, f"{path}[{index}]", omissions)
    elif isinstance(original, dict):
        visible = projected if isinstance(projected, dict) else {}
        missing = [key for key in original if key not in visible]
        if missing:
            omissions.append({"path": path, "omitted_keys": missing})
        for key, item in original.items():
            if key in visible or isinstance(item, (dict, list)):
                _collect_omissions(item, visible.get(key), f"{path}.{key}", omissions)
    elif isinstance(original, str):
        kept = len(projected) - 1 if isinstance(projected, str) else 0
        omissions.append({"path": path, "omitted_characters": len(original) - kept})
    else:
        omissions.append({"path": path, "value_omitted": True})


def _collect_nested_lists(value: Any, path: str, omissions: list[dict[str, Any]]) -> None:
    """An omitted parent covers its scalar fields, but not nested cardinalities."""
    if isinstance(value, list):
        _collect_omissions(value, None, path, omissions)
    elif isinstance(value, dict):
        for key, item in value.items():
            _collect_nested_lists(item, f"{path}.{key}", omissions)
