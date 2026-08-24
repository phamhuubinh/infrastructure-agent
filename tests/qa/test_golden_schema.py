"""Canonical golden schema and coverage tests."""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(
    __file__
).resolve().parents[2]

GOLDEN_DIR = (
    PROJECT_ROOT
    / "tests"
    / "data"
    / "qa_cases"
)

from scripts.qa.build_golden import (  # noqa: E402
    EXPECTED_FIELDS,
    LEGACY_EXPECTED_FIELDS,
    REQUIRED_GROUPS,
    REQUIRED_TAG_COVERAGE,
    load_golden_cases,
    validate_and_report,
)


@pytest.fixture(scope="module")
def golden() -> dict:
    return load_golden_cases(
        GOLDEN_DIR
    )


def test_loads_canonical_schema() -> None:
    doc = load_golden_cases(
        GOLDEN_DIR
    )

    assert doc["schema_version"] == 2
    assert doc["cases"]


def test_no_duplicate_ids(
    golden,
) -> None:
    ids = [
        case["id"]
        for case in golden["cases"]
    ]

    assert len(ids) == len(set(ids))


def test_validation_report_shape() -> None:
    report = validate_and_report(
        GOLDEN_DIR
    )

    assert report[
        "schema_version"
    ] == 2
    assert report["total_cases"] > 0
    assert (
        report["agent_scorable_cases"]
        <= report["total_cases"]
    )


@pytest.mark.parametrize(
    "group",
    sorted(REQUIRED_GROUPS),
)
def test_required_group_coverage(
    golden,
    group,
) -> None:
    groups = {
        case["group"]
        for case in golden["cases"]
    }

    assert group in groups


@pytest.mark.parametrize(
    "tag",
    sorted(
        REQUIRED_TAG_COVERAGE
    ),
)
def test_required_tag_coverage(
    golden,
    tag,
) -> None:
    tags = {
        current
        for case in golden["cases"]
        for current
        in case.get("tags", [])
    }

    assert any(
        tag in current
        or current in tag
        for current in tags
    )


@pytest.mark.parametrize(
    "field",
    EXPECTED_FIELDS,
)
def test_every_case_has_canonical_expected_field(
    golden,
    field,
) -> None:
    for case in golden["cases"]:
        assert field in case["expected"], (
            f"{case['id']}: "
            f"missing expected.{field}"
        )


def test_no_case_keeps_legacy_semantic_expectations(
    golden,
) -> None:
    for case in golden["cases"]:
        legacy = (
            set(case["expected"])
            & LEGACY_EXPECTED_FIELDS
        )

        assert not legacy, (
            f"{case['id']}: "
            f"legacy fields {legacy}"
        )


def test_unknown_target_never_allows_localhost_fallback(
    golden,
) -> None:
    cases = {
        case["id"]: case
        for case in golden["cases"]
    }

    for case_id in (
        "target-unknown-numeric-host",
        "target-unknown-serverabc",
    ):
        expected = cases[
            case_id
        ]["expected"]

        assert "localhost" in (
            expected[
                "forbidden_references"
            ]
        )


def test_external_cases_use_canonical_capabilities(
    golden,
) -> None:
    cases = {
        case["id"]: case
        for case in golden["cases"]
    }

    assert [
        "internet.current"
    ] in cases[
        "ga1-current-external-required"
    ]["expected"][
        "required_capability_sets"
    ]

    assert [
        "internet.fetch_url"
    ] in cases[
        "ga1-explicit-url-fetch"
    ]["expected"][
        "required_capability_sets"
    ]


def test_grafana_only_case_forbids_host_broadening(
    golden,
) -> None:
    cases = {
        case["id"]: case
        for case in golden["cases"]
    }

    expected = cases[
        "ga1-grafana-only-no-broadening"
    ]["expected"]

    assert "grafana." in (
        expected[
            "required_capability_prefixes"
        ]
    )
    assert "host." in (
        expected[
            "forbidden_capability_prefixes"
        ]
    )


def test_prompt_injection_allows_no_action(
    golden,
) -> None:
    cases = {
        case["id"]: case
        for case in golden["cases"]
    }

    expected = cases[
        "edge-action-injection"
    ]["expected"]

    assert expected["terminals"] == [
        "refuse"
    ]
    assert expected[
        "max_actions"
    ] == 0


def test_ids_and_provenance_remain_curated(
    golden,
) -> None:
    for case in golden["cases"]:
        case_id = case["id"]

        assert all(
            char.isalnum()
            or char in "-_"
            for char in case_id
        )

        assert not case_id.startswith(
            "auto_"
        )

        assert case.get("source")
        assert case.get("note")
