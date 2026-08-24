#!/usr/bin/env python3
"""Canonical golden dataset loader and validator for Orion QA.

Golden expectations describe externally observable canonical runtime
contracts. They do not encode deterministic intent parsing, prose target
resolution, answer classifiers, or other legacy semantic internals.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]

SCHEMA_VERSION = 2

VALID_TERMINALS = {
    "final",
    "clarify",
    "refuse",
    "approval_required",
    "failed",
}

EXPECTED_FIELDS = (
    "terminals",
    "required_capability_sets",
    "required_capability_prefixes",
    "forbidden_capability_prefixes",
    "required_references",
    "forbidden_references",
    "min_successful_observations",
    "max_actions",
    "approval_required",
    "failure",
    "response_required",
)

LEGACY_EXPECTED_FIELDS = frozenset(
    {
        "concepts",
        "operation",
        "intent",
        "target",
        "params",
        "answer_type",
        "routing_status",
        "evidence_status",
        "answer_strategy",
        "llm_usage_reason",
        "required_evidence",
        "request_domain",
        "information_scope",
        "external_need",
        "source_constraints",
        "execution_intent",
    }
)

REQUIRED_GROUPS = {
    "A",
    "B",
    "C",
    "D",
    "E",
    "F",
    "G",
    "H",
    "I",
    "J",
}

REQUIRED_TAG_COVERAGE = {
    "vi": "case tiếng Việt",
    "en": "case tiếng Anh",
    "typo": "case typo",
    "code-switching": "case code-switching",
    "follow-up": "case follow-up",
    "unknown": "case unknown target",
    "forecast": "case forecast",
    "injection": "case action injection",
}


class GoldenValidationError(Exception):
    """Raised when the canonical golden dataset violates its contract."""


def _string_list(
    case_id: str,
    field: str,
    value: object,
    *,
    allow_empty: bool = True,
) -> None:
    if not isinstance(value, list):
        raise GoldenValidationError(
            f"{case_id}: expected.{field} must be a list"
        )

    if not allow_empty and not value:
        raise GoldenValidationError(
            f"{case_id}: expected.{field} must not be empty"
        )

    if not all(
        isinstance(item, str) and item
        for item in value
    ):
        raise GoldenValidationError(
            f"{case_id}: expected.{field} must contain strings"
        )


def _validate_context(
    case_id: str,
    value: object,
) -> None:
    if value is None:
        return

    if not isinstance(value, list):
        raise GoldenValidationError(
            f"{case_id}: context must be a list"
        )

    for index, message in enumerate(value):
        if not isinstance(message, dict):
            raise GoldenValidationError(
                f"{case_id}: context[{index}] must be an object"
            )

        if message.get("role") not in {
            "system",
            "user",
            "assistant",
        }:
            raise GoldenValidationError(
                f"{case_id}: context[{index}].role is invalid"
            )

        content = message.get("content")

        if not isinstance(content, str) or not content.strip():
            raise GoldenValidationError(
                f"{case_id}: context[{index}].content must be text"
            )


def validate_cases(
    cases: list[dict[str, Any]],
    groups: dict[str, str],
    *,
    require_coverage: bool = True,
) -> None:
    if not cases:
        raise GoldenValidationError(
            "Golden dataset is empty"
        )

    covered_groups: set[str] = set()
    covered_tags: set[str] = set()

    for case in cases:
        case_id = case.get("id")

        if not isinstance(case_id, str) or not case_id:
            raise GoldenValidationError(
                "case missing id"
            )

        group = case.get("group")

        if group not in groups:
            raise GoldenValidationError(
                f"{case_id}: unknown group {group!r}"
            )

        covered_groups.add(group)

        question = case.get("question")

        if (
            not isinstance(question, str)
            or not question.strip()
        ):
            raise GoldenValidationError(
                f"{case_id}: empty question"
            )

        if not isinstance(
            case.get("source"),
            str,
        ) or not case["source"]:
            raise GoldenValidationError(
                f"{case_id}: missing source"
            )

        if not isinstance(
            case.get("note"),
            str,
        ) or not case["note"]:
            raise GoldenValidationError(
                f"{case_id}: missing note"
            )

        _validate_context(
            case_id,
            case.get("context"),
        )

        expected = case.get("expected")

        if not isinstance(expected, dict):
            raise GoldenValidationError(
                f"{case_id}: missing expected map"
            )

        unexpected_legacy = (
            set(expected)
            & LEGACY_EXPECTED_FIELDS
        )

        if unexpected_legacy:
            raise GoldenValidationError(
                f"{case_id}: legacy expected fields remain: "
                f"{sorted(unexpected_legacy)}"
            )

        missing = [
            field
            for field in EXPECTED_FIELDS
            if field not in expected
        ]

        if missing:
            raise GoldenValidationError(
                f"{case_id}: missing canonical expected fields: "
                f"{missing}"
            )

        _string_list(
            case_id,
            "terminals",
            expected["terminals"],
            allow_empty=False,
        )

        invalid_terminals = (
            set(expected["terminals"])
            - VALID_TERMINALS
        )

        if invalid_terminals:
            raise GoldenValidationError(
                f"{case_id}: invalid terminals: "
                f"{sorted(invalid_terminals)}"
            )

        capability_sets = expected[
            "required_capability_sets"
        ]

        if not isinstance(
            capability_sets,
            list,
        ):
            raise GoldenValidationError(
                f"{case_id}: expected.required_capability_sets "
                "must be a list"
            )

        for index, values in enumerate(
            capability_sets
        ):
            _string_list(
                case_id,
                (
                    "required_capability_sets"
                    f"[{index}]"
                ),
                values,
                allow_empty=False,
            )

        for field in (
            "required_capability_prefixes",
            "forbidden_capability_prefixes",
            "required_references",
            "forbidden_references",
        ):
            _string_list(
                case_id,
                field,
                expected[field],
            )

        for field in (
            "min_successful_observations",
            "max_actions",
        ):
            value = expected[field]

            if (
                type(value) is not int
                or value < 0
            ):
                raise GoldenValidationError(
                    f"{case_id}: expected.{field} "
                    "must be a non-negative integer"
                )

        if (
            type(expected["approval_required"])
            is not bool
        ):
            raise GoldenValidationError(
                f"{case_id}: expected.approval_required "
                "must be boolean"
            )

        if (
            expected["failure"] is not None
            and not isinstance(
                expected["failure"],
                str,
            )
        ):
            raise GoldenValidationError(
                f"{case_id}: expected.failure "
                "must be null or string"
            )

        if (
            type(expected["response_required"])
            is not bool
        ):
            raise GoldenValidationError(
                f"{case_id}: expected.response_required "
                "must be boolean"
            )

        for tag in case.get("tags", []):
            if isinstance(tag, str):
                covered_tags.add(tag)

    if not require_coverage:
        return

    missing_groups = (
        REQUIRED_GROUPS
        - covered_groups
    )

    if missing_groups:
        raise GoldenValidationError(
            "Missing group coverage: "
            f"{sorted(missing_groups)}"
        )

    missing_tags = {
        tag: description
        for tag, description
        in REQUIRED_TAG_COVERAGE.items()
        if not any(
            tag in current
            or current in tag
            for current in covered_tags
        )
    }

    if missing_tags:
        raise GoldenValidationError(
            "Missing required coverage: "
            + ", ".join(
                f"{tag} ({description})"
                for tag, description
                in missing_tags.items()
            )
        )


def load_golden_cases(
    data_dir: Path | None = None,
) -> dict[str, Any]:
    golden_dir = (
        data_dir
        or (
            PROJECT_ROOT
            / "tests"
            / "data"
            / "qa_cases"
        )
    )

    files = sorted(
        golden_dir.glob("*.yaml")
    )

    if not files:
        raise GoldenValidationError(
            f"No golden YAML files found in {golden_dir}"
        )

    doc: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "groups": {},
        "cases": [],
    }

    seen_ids: set[str] = set()

    for path in files:
        loaded = (
            yaml.safe_load(
                path.read_text(
                    encoding="utf-8"
                )
            )
            or {}
        )

        if (
            not isinstance(loaded, dict)
            or loaded.get("schema_version")
            != SCHEMA_VERSION
        ):
            raise GoldenValidationError(
                f"{path}: invalid or missing "
                f"schema_version={SCHEMA_VERSION}"
            )

        groups = loaded.get("groups")
        cases = loaded.get("cases")

        if not isinstance(groups, dict):
            raise GoldenValidationError(
                f"{path}: missing groups"
            )

        if not isinstance(cases, list):
            raise GoldenValidationError(
                f"{path}: missing cases list"
            )

        doc["groups"].update(groups)

        for case in cases:
            if not isinstance(case, dict):
                raise GoldenValidationError(
                    f"{path}: case must be object"
                )

            case_id = case.get("id")

            if case_id in seen_ids:
                raise GoldenValidationError(
                    f"{path}: duplicate case id "
                    f"{case_id!r}"
                )

            seen_ids.add(case_id)
            doc["cases"].append(case)

    validate_cases(
        doc["cases"],
        doc["groups"],
    )

    return doc


def validate_and_report(
    data_dir: Path | None = None,
) -> dict[str, Any]:
    doc = load_golden_cases(data_dir)
    cases = doc["cases"]

    harness = sum(
        1
        for case in cases
        if case.get("harness_error")
    )

    by_group: dict[str, int] = {}

    for case in cases:
        group = case["group"]
        by_group[group] = (
            by_group.get(group, 0) + 1
        )

    return {
        "schema_version": (
            doc["schema_version"]
        ),
        "total_cases": len(cases),
        "harness_error_cases": harness,
        "agent_scorable_cases": (
            len(cases) - harness
        ),
        "groups": sorted(
            doc["groups"]
        ),
        "cases_per_group": by_group,
    }


if __name__ == "__main__":
    try:
        report = validate_and_report()
    except GoldenValidationError as exc:
        print(
            f"Golden validation FAILED: {exc}"
        )
        sys.exit(1)

    print(
        "Canonical golden dataset validation OK"
    )
    print(
        "  schema_version:      "
        f"{report['schema_version']}"
    )
    print(
        "  total cases:         "
        f"{report['total_cases']}"
    )
    print(
        "  harness-error cases: "
        f"{report['harness_error_cases']}"
    )
    print(
        "  agent-scorable:      "
        f"{report['agent_scorable_cases']}"
    )

    for group, count in (
        report["cases_per_group"].items()
    ):
        print(f"    {group}: {count}")
