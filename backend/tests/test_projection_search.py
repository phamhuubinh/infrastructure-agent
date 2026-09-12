"""Adversarial, independent serialization oracle for projection prefix search."""

from __future__ import annotations

import json

import pytest

from orion.chat.model_context import compact_json, project_tool_result
from orion.contracts import ToolResult


def _result(count: int = 30, padding: int = 0) -> ToolResult:
    return ToolResult(
        call_id="nested",
        tool_name="arbitrary.read",
        status="success",
        data=[
            {"id": i, "nested": [1], **({"text": "x" * padding} if padding else {})}
            for i in range(count)
        ],
    )


def _canonical(result: ToolResult) -> dict:
    value = result.model_dump(mode="json")
    value.pop("read_progress")
    return value


def _variants(result: ToolResult, included: int, cap: int) -> list[str]:
    """Enumerate EVERY allowed detail-prefix length, independently of production."""
    original = _canonical(result)
    rows = original["data"]
    omissions = [
        dict(
            path="$.data",
            original_items=len(rows),
            included_items=included,
            omitted_items=len(rows) - included,
        )
    ]
    omissions.extend(
        dict(path=f"$.data[{i}].nested", original_items=1, included_items=0, omitted_items=1)
        for i in range(included, len(rows))
    )
    variants = []
    for retained in range(min(12, len(omissions)) + 1):
        metadata = dict(
            applied=True,
            data_state="partial",
            source_data_state="upstream_nonempty_partial",
            essential_metadata={},
            original_bytes=len(compact_json(original).encode()),
            maximum_bytes=cap,
            omissions=omissions[:retained],
            omission_entries_omitted=len(omissions) - retained,
        )
        if retained < len(omissions):
            metadata["unreported_list_items"] = {
                key: sum(item[key] for item in omissions[retained:])
                for key in ("original_items", "included_items", "omitted_items")
            }
        variants.append(
            compact_json({**original, "data": rows[:included], "_orion_projection": metadata})
        )
    return variants


def test_nested_small_lists_choose_maximal_fitting_prefix() -> None:
    result = _result()
    cap = 600
    assert len(compact_json(_canonical(result)).encode()) == 783 > cap
    candidate = _variants(result, 8, cap)[0]
    assert len(candidate.encode()) == 581 <= cap
    encoded = project_tool_result(result, cap)
    value = json.loads(encoded)
    assert value["data"] == result.data[:8]
    assert encoded == candidate
    assert all(
        len(variant.encode()) > cap for n in range(9, 30) for variant in _variants(result, n, cap)
    )
    assert value["_orion_projection"]["unreported_list_items"] == {
        "original_items": 52,
        "included_items": 8,
        "omitted_items": 44,
    }


def test_nested_omission_cost_is_not_monotonic_in_prefix_length() -> None:
    result = _result()
    # With all detail records retained, adding a row removes a larger omission
    # record. Binary-searching the complete serialized predicate is invalid.
    shorter = _variants(result, 27, 600)[-1]
    longer = _variants(result, 28, 600)[-1]
    assert len(longer.encode()) < len(shorter.encode())


def test_even_minimal_metadata_cost_can_fall_when_a_prefix_grows() -> None:
    result = ToolResult(
        call_id="x", tool_name="arbitrary.read", status="success", data=[[], [], [], "x" * 1000]
    )
    canonical = _canonical(result)
    original_bytes = len(compact_json(canonical).encode())

    def variants(included: int, cap: int) -> list[str]:
        omissions = [
            dict(
                path="$.data", original_items=4, included_items=included, omitted_items=4 - included
            )
        ]
        omissions.extend(
            dict(path=f"$.data[{i}]", original_items=0, included_items=0, omitted_items=0)
            for i in range(included, 3)
        )
        outputs = []
        for retained in range(len(omissions) + 1):
            metadata = dict(
                applied=True,
                data_state="partial",
                source_data_state="upstream_nonempty_partial",
                essential_metadata={},
                original_bytes=original_bytes,
                maximum_bytes=cap,
                omissions=omissions[:retained],
                omission_entries_omitted=len(omissions) - retained,
            )
            if retained < len(omissions):
                metadata["unreported_list_items"] = {
                    key: sum(item[key] for item in omissions[retained:])
                    for key in ("original_items", "included_items", "omitted_items")
                }
            outputs.append(
                compact_json(
                    {**canonical, "data": result.data[:included], "_orion_projection": metadata}
                )
            )
        return outputs

    cap = 398
    assert original_bytes > cap
    # Binary search tests midpoint 2, then 1: both fail although 3 fits, even
    # after trying ALL detail-retention counts at each of those prefixes.
    assert [min(len(value.encode()) for value in variants(n, cap)) for n in (1, 2, 3)] == [
        401,
        404,
        398,
    ]
    assert project_tool_result(result, cap) == variants(3, cap)[-1]
    previous = 0
    for budget in range(330, 400):
        value = json.loads(project_tool_result(result, budget))
        included = len(value["data"] or [])
        assert included >= previous
        previous = included
        fitting = [
            (n, candidate)
            for n in (1, 2, 3)
            for candidate in variants(n, budget)
            if len(candidate.encode()) <= budget
        ]
        if fitting:
            assert included == max(n for n, _ in fitting)


@pytest.mark.parametrize("padding,cap", [(0, 600), (120, 1600), (500, 2200)])
def test_selected_data_keeps_longest_fitting_detail_prefix(padding: int, cap: int) -> None:
    result = _result(padding=padding)
    encoded = project_tool_result(result, cap)
    data = json.loads(encoded)["data"]
    assert data and data == result.data[: len(data)]
    variants = _variants(result, len(data), cap)
    fitting = [value for value in variants if len(value.encode()) <= cap]
    assert fitting and encoded == fitting[-1]
    assert all(
        len(value.encode()) > cap
        for n in range(len(data) + 1, 30)
        for value in _variants(result, n, cap)
    )


def _counts(value, path="$"):  # type: ignore[no-untyped-def]
    result = {}
    if isinstance(value, list):
        result[path] = len(value)
        for i, item in enumerate(value):
            result.update(_counts(item, f"{path}[{i}]"))
    elif isinstance(value, dict):
        for key, item in value.items():
            result.update(_counts(item, f"{path}.{key}"))
    return result


@pytest.mark.parametrize("shape", ["tiny", "list_of_lists", "many_paths"])
def test_nested_prefix_cardinalities_never_decrease_with_budget(shape: str) -> None:
    if shape == "tiny":
        data = _result().data
    elif shape == "list_of_lists":
        data = {"outer": {"rows": [[i, [1], [2]] for i in range(30)]}}
    else:
        data = [{"id": i, "nested": {str(j): [1] for j in range(8)}} for i in range(20)]
    result = ToolResult(call_id="sweep", tool_name="arbitrary.read", status="success", data=data)
    original_size = len(compact_json(_canonical(result)).encode())
    original_counts = _counts(data)
    previous = dict.fromkeys(original_counts, 0)
    for cap in sorted(
        {*range(300, original_size + 5, 7), *range(original_size - 16, original_size + 5)}
    ):
        encoded = project_tool_result(result, cap)
        value = json.loads(encoded)
        current = _counts(value["data"])
        assert all(
            previous[path] <= current.get(path, 0) <= total
            for path, total in original_counts.items()
        ), (shape, cap)
        previous = {path: current.get(path, 0) for path in original_counts}
        assert encoded == project_tool_result(result, cap)
        if len(encoded.encode()) > cap:
            assert value["data"] is None
        if shape == "tiny" and value["data"] and cap < original_size:
            included = len(value["data"])
            # Exhaustive oracle rules out EVERY longer whole-row prefix and
            # EVERY detail-retention count, not just monotonic data_state.
            assert all(
                len(variant.encode()) > cap
                for n in range(included + 1, 30)
                for variant in _variants(result, n, cap)
            )


@pytest.mark.parametrize("ending", ["", "…"])
def test_partial_string_search_matches_exhaustive_costs(ending: str) -> None:
    # Escape sequences, multibyte text and decimal omitted-count boundaries.
    data = ('é🙂\\"' * 28) + ending
    result = ToolResult(call_id="string", tool_name="arbitrary.read", status="success", data=data)
    canonical = _canonical(result)
    original_size = len(compact_json(canonical).encode())
    for cap in range(300, original_size, 11):
        candidates = []
        for length in range(1, len(data)):
            partial = data[:length] + "…"
            if partial == data:
                continue
            variants = []
            for retained in [0, 1]:
                metadata = dict(
                    applied=True,
                    data_state="partial",
                    source_data_state="upstream_nonempty_partial",
                    essential_metadata={},
                    original_bytes=original_size,
                    maximum_bytes=cap,
                    omissions=(
                        [dict(path="$.data", omitted_characters=len(data) - length)]
                        if retained
                        else []
                    ),
                    omission_entries_omitted=1 - retained,
                )
                encoded = compact_json(
                    {**canonical, "data": partial, "_orion_projection": metadata}
                )
                if len(encoded.encode()) <= cap:
                    variants.append(encoded)
            if variants:
                candidates.append(variants[-1])
        if candidates:
            assert project_tool_result(result, cap) == candidates[-1]


def test_large_list_search_work_is_bounded_by_cap_not_list_length(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import orion.chat.model_context as projection

    result = _result(count=10_000)
    cap = 6000
    sizes = []
    root_candidates = 0
    serialize = projection.compact_json
    collect = projection._collect_omissions

    def measured_serialize(value):  # type: ignore[no-untyped-def]
        encoded = serialize(value)
        sizes.append(len(encoded.encode()))
        return encoded

    def measured_collect(original, projected, path, omissions):  # type: ignore[no-untyped-def]
        nonlocal root_candidates
        if path == "$.data":
            root_candidates += 1
        return collect(original, projected, path, omissions)

    monkeypatch.setattr(projection, "compact_json", measured_serialize)
    monkeypatch.setattr(projection, "_collect_omissions", measured_collect)
    encoded = project_tool_result(result, cap)
    projected = json.loads(encoded)
    assert projected["data"] == result.data[: len(projected["data"])]
    assert 200 < len(projected["data"]) < 300
    assert len(encoded.encode()) <= cap
    # Data-only costs preclude every prefix >= 255 for this fixture, even though
    # the input has 10,000 rows. No sequence of full-N serializations is allowed.
    assert root_candidates <= 254
    assert sum(size > 2 * cap for size in sizes) == 1  # canonical, once
    assert sum(sizes) < sizes[0] + 254 * 14 * (2 * cap)
