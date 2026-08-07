#!/usr/bin/env python3
"""Evaluate stage-level Orion acceptance gates from a baseline JSON report.

The report is normally produced by ``scripts/qa/run_baseline.py``.  Keeping
execution and gate evaluation separate lets CI test exactly the same gates
against deterministic fixture reports, without a configured model or a live
developer machine.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.qa.acceptance_gates import evaluate_acceptance_gates, write_report


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Acceptance input must be a JSON object: {path}")
    return value


def run_acceptance(
    report: dict,
    *,
    baseline: dict | None = None,
) -> dict:
    """Return the machine-readable result used by CI and tests."""
    return evaluate_acceptance_gates(report, baseline=baseline).to_dict()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Orion acceptance gates.")
    parser.add_argument("--report", required=True, help="Stage baseline JSON report.")
    parser.add_argument(
        "--baseline",
        help="Optional prior stage baseline JSON used for latency regression gates.",
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts/qa",
        help="Directory for JSON/Markdown gate artifacts.",
    )
    args = parser.parse_args()

    try:
        report = _load(Path(args.report))
        baseline = _load(Path(args.baseline)) if args.baseline else None
        result = evaluate_acceptance_gates(report, baseline=baseline)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    json_path, markdown_path = write_report(result, Path(args.output_dir))
    print(f"Acceptance JSON: {json_path}")
    print(f"Acceptance Markdown: {markdown_path}")
    print(f"Acceptance status: {'PASS' if result.passed else 'FAIL'}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
