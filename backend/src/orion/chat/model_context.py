"""Bounded, structure-preserving projections for model-visible tool data."""

from __future__ import annotations

import json
from typing import Any

from orion.contracts import ToolResult

_PROJECTION_RESERVE_BYTES = 768
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
    "segment_count",
    "total_segments",
}


def compact_json(value: object) -> str:
    """Serialize deterministic model data without insignificant JSON whitespace."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def project_tool_result(result: ToolResult, maximum_bytes: int) -> str:
    """Return a bounded model-only projection while leaving the canonical result untouched.

    Status, errors, correlation metadata, and exact SourceRef objects are never reduced.
    The byte limit is soft only when that irreducible envelope itself exceeds it.
    """
    canonical = result.model_dump(mode="json")
    serialized = compact_json(canonical)
    original_bytes = len(serialized.encode("utf-8"))
    if original_bytes <= maximum_bytes:
        return serialized

    envelope = {key: value for key, value in canonical.items() if key != "data"}
    envelope["data"] = None
    envelope["_orion_projection"] = {
        "applied": True,
        "original_bytes": original_bytes,
        "maximum_bytes": maximum_bytes,
        "omissions": [],
        "omission_entries_omitted": 0,
    }
    irreducible_bytes = len(compact_json(envelope).encode("utf-8"))
    data_budget = max(0, maximum_bytes - irreducible_bytes - _PROJECTION_RESERVE_BYTES)

    projected: dict[str, Any] = envelope
    for _ in range(4):
        omissions: list[dict[str, Any]] = []
        projected_data = _project_value(canonical.get("data"), data_budget, "$.data", omissions)
        projected = {
            **{key: value for key, value in canonical.items() if key != "data"},
            "data": projected_data,
            "_orion_projection": {
                "applied": True,
                "original_bytes": original_bytes,
                "maximum_bytes": maximum_bytes,
                "omissions": omissions[:_MAX_OMISSION_RECORDS],
                "omission_entries_omitted": max(0, len(omissions) - _MAX_OMISSION_RECORDS),
            },
        }
        projected_bytes = len(compact_json(projected).encode("utf-8"))
        if projected_bytes <= maximum_bytes or data_budget == 0:
            break
        data_budget = max(0, data_budget - (projected_bytes - maximum_bytes) - 32)
    return compact_json(projected)


def _project_value(value: Any, budget: int, path: str, omissions: list[dict[str, Any]]) -> Any:
    if _json_bytes(value) <= budget:
        return value
    if isinstance(value, str):
        return _project_string(value, budget, path, omissions)
    if isinstance(value, list):
        return _project_list(value, budget, path, omissions)
    if isinstance(value, dict):
        return _project_dict(value, budget, path, omissions)
    omissions.append({"path": path, "value_omitted": True})
    return None


def _project_string(
    value: str, budget: int, path: str, omissions: list[dict[str, Any]]
) -> str | None:
    if budget < 5:
        omissions.append({"path": path, "omitted_characters": len(value)})
        return None
    low, high = 0, len(value)
    while low < high:
        middle = (low + high + 1) // 2
        candidate = value[:middle] + "…"
        if _json_bytes(candidate) <= budget:
            low = middle
        else:
            high = middle - 1
    omissions.append({"path": path, "omitted_characters": len(value) - low})
    return value[:low] + "…"


def _project_list(
    value: list[Any], budget: int, path: str, omissions: list[dict[str, Any]]
) -> list[Any]:
    projected: list[Any] = []
    for index, item in enumerate(value):
        remaining = budget - _json_bytes(projected) - (1 if projected else 0)
        if remaining <= 2:
            break
        if _json_bytes(item) <= remaining:
            projected.append(item)
            continue
        if not projected:
            reduced = _project_value(item, remaining, f"{path}[{index}]", omissions)
            if reduced is not None:
                projected.append(reduced)
        break
    if len(projected) < len(value):
        omissions.append(
            {
                "path": path,
                "original_items": len(value),
                "included_items": len(projected),
                "omitted_items": len(value) - len(projected),
            }
        )
    return projected


def _project_dict(
    value: dict[str, Any], budget: int, path: str, omissions: list[dict[str, Any]]
) -> dict[str, Any]:
    projected: dict[str, Any] = {}
    positions = {key: index for index, key in enumerate(value)}
    keys = sorted(value, key=lambda key: (key not in _PRIORITY_KEYS, positions[key]))
    omitted_keys: list[str] = []
    for index, key in enumerate(keys):
        remaining = budget - _json_bytes(projected) - _json_bytes(key) - 2
        if remaining <= 0:
            _record_omitted_key(value, key, path, omissions, omitted_keys)
            continue
        item = value[key]
        # Share the remaining value space across every unprocessed key. Small
        # scalars consume less than their share, so later collections inherit the
        # unused space. A large early details field cannot starve all later keys.
        value_budget = max(0, remaining // (len(keys) - index))
        if value_budget == 0:
            _record_omitted_key(value, key, path, omissions, omitted_keys)
            continue
        reduced = (
            item
            if _json_bytes(item) <= value_budget
            else _project_value(item, value_budget, f"{path}.{key}", omissions)
        )
        candidate = {**projected, key: reduced}
        if _json_bytes(candidate) <= budget:
            projected[key] = reduced
        else:
            _record_omitted_key(value, key, path, omissions, omitted_keys)
    if omitted_keys:
        omissions.append({"path": path, "omitted_keys": omitted_keys})
    return projected


def _record_omitted_key(
    value: dict[str, Any],
    key: str,
    path: str,
    omissions: list[dict[str, Any]],
    omitted_keys: list[str],
) -> None:
    item = value[key]
    if isinstance(item, list):
        omissions.append(
            {
                "path": f"{path}.{key}",
                "original_items": len(item),
                "included_items": 0,
                "omitted_items": len(item),
            }
        )
    else:
        omitted_keys.append(key)


def _json_bytes(value: object) -> int:
    return len(compact_json(value).encode("utf-8"))
