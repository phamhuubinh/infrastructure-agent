"""Create the standard QA dashboard artifacts from a stage-level report."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.qa.acceptance_gates import evaluate_acceptance_gates, render_markdown
from scripts.qa.run_baseline import render_markdown as render_stage_markdown


def generate_standard_report(
    stage_report: dict,
    *,
    baseline: dict | None = None,
) -> tuple[dict, str]:
    """Return JSON and Markdown with stage, language, safety and budget views."""
    gates = evaluate_acceptance_gates(stage_report, baseline=baseline)
    payload = {
        "stage_summary": stage_report.get("summary", {}),
        "diagnostics": stage_report.get("diagnostics", {}),
        "acceptance": gates.to_dict(),
    }
    if "metadata" in stage_report:
        stage_markdown = render_stage_markdown(stage_report)
    else:
        stage_markdown = (
            "# Orion Stage QA Report\n\nFixture report without run metadata.\n"
        )
    markdown = stage_markdown + "\n" + render_markdown(gates)
    return payload, markdown


def write_standard_report(
    stage_report: dict,
    output_dir: Path,
    *,
    baseline: dict | None = None,
) -> tuple[Path, Path]:
    """Write the machine-readable and human-readable QA dashboard artifacts."""
    payload, markdown = generate_standard_report(stage_report, baseline=baseline)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "qa_report.json"
    markdown_path = output_dir / "qa_report.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    markdown_path.write_text(markdown, encoding="utf-8")
    return json_path, markdown_path
