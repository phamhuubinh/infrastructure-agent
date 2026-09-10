#!/usr/bin/env python3
"""Offline quality-review overlay for immutable Orion QA execution artifacts.

This module deliberately does not import the QA runner.  It only reads an existing
``manifest.json``, ``cases.jsonl``, and optional reviewer-owned JSONL sidecar; it
does not start an API, load a model profile, or modify execution results.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

QUALITY_VERDICT_SCHEMA_VERSION = 1
VERDICTS = frozenset({"accepted", "rejected", "not_assessable"})
QUALITY_SIDECAR_NAME = "quality-verdicts.jsonl"


class QualityArtifactError(ValueError):
    """An offline QA artifact or its reviewer sidecar is malformed."""


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _sha256(value: object) -> str:
    if isinstance(value, str):
        encoded = value.encode("utf-8")
    else:
        encoded = _canonical_json(value).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise QualityArtifactError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise QualityArtifactError(f"{path} must contain a JSON object")
    return value


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise QualityArtifactError(f"cannot read {path}: {error}") from error
    values: list[dict[str, object]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise QualityArtifactError(
                f"invalid JSON at {path}:{line_number}: {error}"
            ) from error
        if not isinstance(value, dict):
            raise QualityArtifactError(
                f"{path}:{line_number} must contain a JSON object"
            )
        values.append(value)
    return values


def load_artifact(
    report_directory: Path,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Load an artifact without modifying it."""
    return (
        _read_json(report_directory / "manifest.json"),
        _read_jsonl(report_directory / "cases.jsonl"),
    )


def run_identity(report_directory: Path, manifest: dict[str, object]) -> dict[str, str]:
    """Return the immutable identity a reviewer sidecar must bind to."""
    provenance = manifest.get("execution_provenance")
    fingerprint = (
        provenance.get("fingerprint")
        if isinstance(provenance, dict)
        and isinstance(provenance.get("fingerprint"), str)
        else "unknown"
    )
    return {
        "run_id": report_directory.name,
        "manifest_sha256": _sha256(manifest),
        "execution_fingerprint": fingerprint,
    }


def _diagnostic_complete(diagnostic: object) -> tuple[bool, str | None, str | None]:
    """Return whether a diagnostic contains one reviewable terminal answer/evidence."""
    if not isinstance(diagnostic, dict):
        return False, None, "quality evidence is absent"
    if diagnostic.get("events_truncated") is True:
        return False, None, "quality evidence events are truncated"
    events = diagnostic.get("events")
    if not isinstance(events, list):
        return False, None, "quality evidence events are absent"
    terminal_answers: list[str] = []
    for event in events:
        if not isinstance(event, dict):
            return False, None, "quality evidence has malformed event"
        if any(
            value is True for key, value in event.items() if key.endswith("_truncated")
        ):
            return False, None, "quality evidence is truncated"
        if event.get("kind") != "assistant_message" or not event.get(
            "terminal_response"
        ):
            continue
        content = event.get("content")
        if event.get("hidden_reasoning_omitted") is True:
            return False, None, "terminal answer is unavailable for review"
        if not isinstance(content, str) or not content.strip():
            return False, None, "terminal answer is absent"
        terminal_answers.append(content)
    if not terminal_answers:
        return False, None, "terminal answer is absent"
    # The transcript digest below still binds every terminal event.  The final one is
    # the answer a reviewer sees as the terminal response to this case.
    return True, terminal_answers[-1], None


def review_subject(
    report_directory: Path, manifest: dict[str, object], result: dict[str, object]
) -> dict[str, object]:
    """Build hashes and reviewability state for one case without judging its content."""
    phase = result.get("phase", "structured")
    case_id = result.get("id")
    if (
        not isinstance(phase, str)
        or not phase
        or not isinstance(case_id, str)
        or not case_id
    ):
        raise QualityArtifactError("case result is missing a non-empty phase or id")
    if result.get("status") != "MANUAL_REVIEW":
        complete, answer, reason = (
            False,
            None,
            "execution did not reach reviewable terminal outcome (MANUAL_REVIEW)",
        )
    else:
        complete, answer, reason = _diagnostic_complete(
            result.get("stability_diagnostic")
        )
    subject: dict[str, object] = {
        **run_identity(report_directory, manifest),
        "phase": phase,
        "case_id": case_id,
        "reviewable": complete,
        "reason": reason,
    }
    if complete:
        assert answer is not None
        subject["answer_sha256"] = _sha256(answer)
        subject["evidence_sha256"] = _sha256(result["stability_diagnostic"])
    return subject


def _required_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise QualityArtifactError(f"review verdict has invalid {name}")
    return value


def _verdict_identity(verdict: dict[str, object]) -> tuple[str, str]:
    return (
        _required_string(verdict.get("phase"), "phase"),
        _required_string(verdict.get("case_id"), "case_id"),
    )


def validate_verdict(
    verdict: dict[str, object], subject: dict[str, object]
) -> str | None:
    """Validate a reviewer decision against exactly one run, case, answer and evidence."""
    if verdict.get("schema_version") != QUALITY_VERDICT_SCHEMA_VERSION:
        return "unsupported schema_version"
    if verdict.get("verdict") not in VERDICTS:
        return "invalid verdict"
    try:
        for field in (
            "run_id",
            "manifest_sha256",
            "execution_fingerprint",
            "phase",
            "case_id",
            "answer_sha256",
            "evidence_sha256",
            "rationale",
            "reviewer",
            "reviewed_at",
        ):
            value = _required_string(verdict.get(field), field)
            if field in subject and value != subject[field]:
                return f"{field} does not match this artifact"
    except QualityArtifactError as error:
        return str(error)
    if not subject.get("reviewable"):
        return str(subject.get("reason") or "quality evidence is not reviewable")
    return None


def _sidecars_by_case(
    sidecars: list[dict[str, object]],
) -> tuple[dict[tuple[str, str], list[dict[str, object]]], list[str]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
    errors: list[str] = []
    for index, verdict in enumerate(sidecars, start=1):
        try:
            grouped.setdefault(_verdict_identity(verdict), []).append(verdict)
        except QualityArtifactError as error:
            errors.append(f"sidecar entry {index}: {error}")
    return grouped, errors


def aggregate_quality(
    report_directory: Path,
    manifest: dict[str, object],
    results: list[dict[str, object]],
    sidecars: list[dict[str, object]] = (),
) -> dict[str, object]:
    """Aggregate execution and quality status without changing either source artifact."""
    grouped, errors = _sidecars_by_case(sidecars)
    cases: list[dict[str, object]] = []
    for result in results:
        phase = result.get("phase", "structured")
        case_id = result.get("id")
        execution_status = result.get("status")
        if (
            not isinstance(phase, str)
            or not isinstance(case_id, str)
            or not isinstance(execution_status, str)
        ):
            raise QualityArtifactError(
                "case result is missing phase, id, or execution status"
            )
        item: dict[str, object] = {
            "phase": phase,
            "case_id": case_id,
            "execution_status": execution_status,
            "manual_quality": bool(result.get("manual_quality")),
        }
        if "manual_quality" not in result:
            item["quality_status"] = "unknown"
            item["quality_reason"] = "legacy artifact has no manual_quality marker"
            cases.append(item)
            continue
        if not bool(result.get("manual_quality")):
            item["quality_status"] = "not_required"
            cases.append(item)
            continue
        subject = review_subject(report_directory, manifest, result)
        item["review_subject"] = subject
        matches = grouped.get((phase, case_id), [])
        if len(matches) > 1:
            item["quality_status"] = (
                "pending_review" if subject["reviewable"] else "not_assessable"
            )
            item["quality_reason"] = (
                "duplicate reviewer verdicts for this run/phase/case"
                if subject["reviewable"]
                else f"{subject['reason']}; duplicate reviewer verdicts rejected"
            )
        elif len(matches) == 1:
            error = validate_verdict(matches[0], subject)
            if error is not None:
                item["quality_status"] = (
                    "pending_review" if subject["reviewable"] else "not_assessable"
                )
                item["quality_reason"] = f"review verdict rejected: {error}"
            else:
                item["quality_status"] = matches[0]["verdict"]
                item["reviewer"] = matches[0]["reviewer"]
                item["reviewed_at"] = matches[0]["reviewed_at"]
                item["quality_rationale"] = matches[0]["rationale"]
        elif subject["reviewable"]:
            item["quality_status"] = "pending_review"
            item["quality_reason"] = "no reviewer verdict sidecar"
        else:
            item["quality_status"] = "not_assessable"
            item["quality_reason"] = subject["reason"]
        cases.append(item)
    counts = Counter(str(item["quality_status"]) for item in cases)
    execution_counts = Counter(str(item["execution_status"]) for item in cases)
    return {
        "schema_version": QUALITY_VERDICT_SCHEMA_VERSION,
        "run_identity": run_identity(report_directory, manifest),
        "execution": dict(sorted(execution_counts.items())),
        "quality": dict(sorted(counts.items())),
        "sidecar_errors": errors,
        "cases": cases,
    }


def quality_gate(
    aggregate: dict[str, object],
    *,
    skip_policy: str | None,
    skip_rationale: str | None = None,
) -> dict[str, object]:
    """Apply the explicit offline release gate; a false result must exit nonzero."""
    cases = aggregate.get("cases")
    if not isinstance(cases, list):
        raise QualityArtifactError("quality aggregate has no cases")
    failures: list[str] = []
    automatic_failures = [
        item
        for item in cases
        if isinstance(item, dict) and item.get("execution_status") == "FAIL"
    ]
    if automatic_failures:
        failures.append(f"automatic FAIL in {len(automatic_failures)} case(s)")
    quality_failures = [
        item
        for item in cases
        if isinstance(item, dict)
        and item.get("manual_quality") is True
        and item.get("quality_status") != "accepted"
    ]
    if quality_failures:
        failures.append(
            f"required quality review is not accepted for {len(quality_failures)} case(s)"
        )
    skipped = [
        item
        for item in cases
        if isinstance(item, dict) and item.get("execution_status") == "SKIP"
    ]
    if skip_policy not in {"forbid", "allow-with-rationale"}:
        failures.append("a skip coverage policy is required")
    elif skip_policy == "forbid" and skipped:
        failures.append(
            f"SKIP is forbidden by coverage policy ({len(skipped)} case(s))"
        )
    elif skip_policy == "allow-with-rationale" and (
        not isinstance(skip_rationale, str) or not skip_rationale.strip()
    ):
        failures.append("skip coverage policy requires a non-empty rationale")
    sidecar_errors = aggregate.get("sidecar_errors")
    if isinstance(sidecar_errors, list) and sidecar_errors:
        failures.append(f"invalid sidecar entries: {len(sidecar_errors)}")
    return {
        "gate": "orion-qa-quality-gate",
        "passed": not failures,
        "failures": failures,
        "skip_policy": skip_policy,
        "skip_rationale": skip_rationale
        if skip_policy == "allow-with-rationale"
        else None,
        "aggregate": aggregate,
    }


def _load_sidecars(path: Path | None) -> list[dict[str, object]]:
    return [] if path is None or not path.exists() else _read_jsonl(path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only Orion QA quality-verdict overlay"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("inspect", "gate"):
        command = commands.add_parser(name)
        command.add_argument("report_directory", type=Path)
        command.add_argument("--sidecar", type=Path)
        command.add_argument(
            "--output", type=Path, help="write only a separate overlay report"
        )
        if name == "gate":
            command.add_argument(
                "--skip-policy",
                choices=("forbid", "allow-with-rationale"),
                required=True,
            )
            command.add_argument("--skip-rationale")
    return parser


def main(arguments: list[str] | None = None) -> int:
    args = _parser().parse_args(arguments)
    try:
        manifest, results = load_artifact(args.report_directory)
        sidecar = args.sidecar or args.report_directory / QUALITY_SIDECAR_NAME
        aggregate = aggregate_quality(
            args.report_directory, manifest, results, _load_sidecars(sidecar)
        )
        output: dict[str, object]
        if args.command == "gate":
            output = quality_gate(
                aggregate,
                skip_policy=args.skip_policy,
                skip_rationale=args.skip_rationale,
            )
        else:
            output = aggregate
        serialized = json.dumps(output, indent=2, ensure_ascii=False) + "\n"
        if args.output is not None:
            args.output.write_text(serialized, encoding="utf-8")
        sys.stdout.write(serialized)
        return 0 if args.command != "gate" or output["passed"] else 1
    except QualityArtifactError as error:
        print(f"quality verdict preflight failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
