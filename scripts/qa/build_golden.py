#!/usr/bin/env python3
"""Golden dataset loader and validator for stage-level QA scoring (DR1-004).

This module loads the human-reviewed golden cases from
``tests/data/qa_cases/*.yaml`` and validates them against the stage-level
taxonomy used by the pipeline so a stage scorer (DR1-005/DR1-807) can rely on
the dataset without guessing keys.

The golden dataset is deliberately NOT auto-generated output: every case is a
curated expectation reviewed against real transcripts. ``harness_error: true``
marks cases whose transcript failure came from the harness/runner rather than
the agent, so they are excluded from agent pass/fail scoring.

Run directly to print a validation report::

    python3 scripts/qa/build_golden.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# Enum taxonomies (must match src/pipeline enums — values are names only)
# ---------------------------------------------------------------------------
VALID_INTENTS = {
    "CPU_ASSESSMENT",
    "MEMORY_ASSESSMENT",
    "DISK_ASSESSMENT",
    "NETWORK_ASSESSMENT_SINGLE",
    "NETWORK_ASSESSMENT",
    "PROCESS_ASSESSMENT",
    "FILESYSTEM_ASSESSMENT",
    "MACHINE_ASSESSMENT",
    "APPLICATION_DISCOVERY",
    "SERVICE_ASSESSMENT",
    "MONITORING_ASSESSMENT",
    "SECURITY_ASSESSMENT",
    "PERFORMANCE_ASSESSMENT",
    "STORAGE_ASSESSMENT",
    "CONFIGURATION_ASSESSMENT",
    "TROUBLESHOOTING",
    "KNOWLEDGE_ASSESSMENT",
}

VALID_ANSWER_TYPES = {"FACT", "LIST", "TABLE", "CHART", "COMPARISON", "ASSESSMENT"}

VALID_ANSWER_STRATEGIES = {
    "DETERMINISTIC_FACT",
    "LLM_ASSESSMENT",
    "DETERMINISTIC_RESPONDER",
    "CLARIFICATION",
    "REFUSAL",
    "CHAT",
}

VALID_LLM_USAGE_REASONS = {
    "EXPECTED_ASSESSMENT",
    "ROUTING_FALLBACK",
    "INSUFFICIENT_EVIDENCE",
    "NONE",
}

VALID_ROUTING_STATUSES = {
    "resolved",
    "clarification_required",
    "fallback",
    "unsupported",
    "chat",
}

VALID_EVIDENCE_STATUSES = {
    "sufficient",
    "partial",
    "unavailable",
    "stale",
    "contradictory",
    "not_applicable",
}

VALID_OPERATIONS = {"inspect", "diagnose", "summarize"}

REQUIRED_GROUPS = {"A", "B", "C", "D", "E", "F", "G", "H", "I", "J"}

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
    """Raised when the golden dataset violates the schema or coverage rules."""


def load_golden_cases(data_dir: Path | None = None) -> dict[str, Any]:
    """Load and validate all ``*.yaml`` golden files in ``tests/data/qa_cases``."""
    golden_dir = data_dir or (PROJECT_ROOT / "tests" / "data" / "qa_cases")
    files = sorted(golden_dir.glob("*.yaml"))
    if not files:
        raise GoldenValidationError(f"No golden YAML files found in {golden_dir}")

    doc: dict[str, Any] = {"schema_version": 1, "groups": {}, "cases": []}
    seen_ids: set[str] = set()
    for path in files:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict) or loaded.get("schema_version") != 1:
            raise GoldenValidationError(f"{path}: invalid or missing schema_version=1")
        if not loaded.get("groups"):
            raise GoldenValidationError(f"{path}: missing 'groups'")
        if not isinstance(loaded.get("cases"), list):
            raise GoldenValidationError(f"{path}: missing 'cases' list")

        doc["groups"].update(loaded["groups"])
        for case in loaded["cases"]:
            case_id = case.get("id")
            if not case_id:
                raise GoldenValidationError(f"{path}: case missing 'id'")
            if case_id in seen_ids:
                raise GoldenValidationError(f"{path}: duplicate case id '{case_id}'")
            seen_ids.add(case_id)
            doc["cases"].append(case)

    _validate_cases(doc["cases"], doc["groups"])
    return doc


def _validate_cases(cases: list[dict[str, Any]], groups: dict[str, str]) -> None:
    if len(cases) == 0:
        raise GoldenValidationError("Golden dataset is empty")

    # Case-level schema
    covered_groups: set[str] = set()
    covered_tags: set[str] = set()
    for case in cases:
        group = case.get("group")
        if group not in groups:
            raise GoldenValidationError(f"{case['id']}: unknown group '{group}'")
        covered_groups.add(group)

        question = case.get("question")
        if not question or not question.strip():
            raise GoldenValidationError(f"{case['id']}: empty question")

        if not isinstance(case.get("expected"), dict):
            raise GoldenValidationError(f"{case['id']}: missing 'expected' map")
        exp = case["expected"]

        for field in (
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
        ):
            if field not in exp:
                raise GoldenValidationError(f"{case['id']}: missing expected.{field}")

        for field in ("concepts", "params", "required_evidence"):
            if not isinstance(exp[field], (list, dict)):
                raise GoldenValidationError(
                    f"{case['id']}: expected.{field} must be list/dict"
                )

        if exp["operation"] is not None and exp["operation"] not in VALID_OPERATIONS:
            raise GoldenValidationError(
                f"{case['id']}: invalid operation '{exp['operation']}'"
            )
        if exp["intent"] is not None and exp["intent"] not in VALID_INTENTS:
            raise GoldenValidationError(
                f"{case['id']}: invalid intent '{exp['intent']}'"
            )
        if (
            exp["answer_type"] is not None
            and exp["answer_type"] not in VALID_ANSWER_TYPES
        ):
            raise GoldenValidationError(
                f"{case['id']}: invalid answer_type '{exp['answer_type']}'"
            )
        if exp["answer_strategy"] not in VALID_ANSWER_STRATEGIES:
            raise GoldenValidationError(
                f"{case['id']}: invalid answer_strategy '{exp['answer_strategy']}'"
            )
        if exp["llm_usage_reason"] not in VALID_LLM_USAGE_REASONS:
            raise GoldenValidationError(
                f"{case['id']}: invalid llm_usage_reason '{exp['llm_usage_reason']}'"
            )
        if exp["routing_status"] not in VALID_ROUTING_STATUSES:
            raise GoldenValidationError(
                f"{case['id']}: invalid routing_status '{exp['routing_status']}'"
            )
        if exp["evidence_status"] not in VALID_EVIDENCE_STATUSES:
            raise GoldenValidationError(
                f"{case['id']}: invalid evidence_status '{exp['evidence_status']}'"
            )

        # Sanity: deterministic strategies imply no LLM; chat/refusal have no intent
        if exp["answer_strategy"] in (
            "DETERMINISTIC_FACT",
            "DETERMINISTIC_RESPONDER",
            "CHAT",
            "REFUSAL",
            "CLARIFICATION",
        ):
            if exp["llm_usage_reason"] == "EXPECTED_ASSESSMENT":
                raise GoldenValidationError(
                    f"{case['id']}: deterministic/chat/refusal strategy cannot use EXPECTED_ASSESSMENT"
                )
        if exp["routing_status"] == "chat" and exp["intent"] is not None:
            raise GoldenValidationError(
                f"{case['id']}: chat routing must not carry an intent"
            )
        if (
            exp["routing_status"] == "unsupported"
            and exp["intent"] is None
            and exp["answer_type"] is not None
        ):
            raise GoldenValidationError(
                f"{case['id']}: unsupported routing with no intent must not carry an answer_type"
            )

        # Tag coverage scan (coarse: any tag containing the key counts)
        for tag in case.get("tags", []):
            covered_tags.add(tag)

    # Group coverage A-J
    missing = REQUIRED_GROUPS - covered_groups
    if missing:
        raise GoldenValidationError(f"Missing group coverage: {sorted(missing)}")

    # Required edge-case coverage
    missing_tags: dict[str, str] = {}
    for tag, label in REQUIRED_TAG_COVERAGE.items():
        if not any(tag in t or t in tag for t in covered_tags):
            missing_tags[tag] = label
    if missing_tags:
        raise GoldenValidationError(
            "Missing required coverage: "
            + ", ".join(f"{k} ({v})" for k, v in missing_tags.items())
        )


def validate_and_report(data_dir: Path | None = None) -> dict[str, Any]:
    """Validate the dataset and return a summary dict for reporting."""
    doc = load_golden_cases(data_dir)
    cases = doc["cases"]
    total = len(cases)
    harness = sum(1 for c in cases if c.get("harness_error"))
    by_group: dict[str, int] = {}
    for c in cases:
        by_group[c["group"]] = by_group.get(c["group"], 0) + 1
    return {
        "schema_version": doc["schema_version"],
        "total_cases": total,
        "harness_error_cases": harness,
        "agent_scorable_cases": total - harness,
        "groups": sorted(doc["groups"]),
        "cases_per_group": by_group,
    }


if __name__ == "__main__":
    try:
        report = validate_and_report()
    except GoldenValidationError as exc:
        print(f"Golden validation FAILED: {exc}")
        sys.exit(1)
    print("Golden dataset validation OK")
    print(f"  schema_version:      {report['schema_version']}")
    print(f"  total cases:         {report['total_cases']}")
    print(f"  harness-error cases: {report['harness_error_cases']}")
    print(f"  agent-scorable:      {report['agent_scorable_cases']}")
    print(
        f"  groups covered:      {len(report['groups'])} ({len(report['cases_per_group'])} with cases)"
    )
    for gid in report["cases_per_group"]:
        print(f"    {gid}: {report['cases_per_group'][gid]}")
