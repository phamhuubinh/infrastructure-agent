"""Integration test: invoke benchmark.__main__.main() directly.

This test calls main() with sys.argv set to --domain assessment --json,
captures real stdout, and asserts the JSON output contains a "benchmark"
metadata key.

Unlike test_report_wiring.py (which calls generate_json_report() directly
with a hand-built metadata dict), this test exercises the actual CLI call path
that a user executes with "python -m benchmark --domain assessment --json".

If main() regresses to calling generate_json_report(results) without passing
metadata, this test will FAIL — proving it catches the Phase 5-style wiring gap.
"""

import json
import sys
from io import StringIO
from unittest import mock

from benchmark.__main__ import main


def test_main_json_output_contains_benchmark_metadata() -> None:
    """main() with --json must emit a "benchmark" key in the JSON output."""
    old_stdout = sys.stdout
    sys.stdout = StringIO()

    with mock.patch(
        "src.model.llm_client.LLMClient.generate",
        return_value="Mocked assessment result for benchmark test.",
    ):
        try:
            main(["--domain", "assessment", "--json"])
        except SystemExit:
            pass

    output = sys.stdout.getvalue()
    sys.stdout = old_stdout

    # Find the JSON object at the end of the output.
    start = output.find("{")
    end = output.rfind("}") + 1
    json_str = output[start:end]

    data = json.loads(json_str)

    assert "benchmark" in data, (
        f"CLI output missing 'benchmark' key. "
        f"This proves main() is NOT passing metadata to generate_json_report(). "
        f"Available keys: {list(data.keys())}. "
        f"This test must fail when the wiring is broken. "
        f"Phase 5 had the same symptom — metadata collected but never passed to report."
    )

    bm = data["benchmark"]
    assert "model" in bm, f"Missing 'model' in metadata: {list(bm.keys())}"
    assert "server" in bm
    assert "captured_at" in bm


def test_main_json_structure() -> None:
    """Verify overall JSON structure from main()."""
    old_stdout = sys.stdout
    sys.stdout = StringIO()

    with mock.patch(
        "src.model.llm_client.LLMClient.generate",
        return_value="Mocked assessment result for benchmark test.",
    ):
        try:
            main(["--domain", "assessment", "--json"])
        except SystemExit:
            pass

    output = sys.stdout.getvalue()
    sys.stdout = old_stdout

    start = output.find("{")
    end = output.rfind("}") + 1
    data = json.loads(output[start:end])

    assert "overall" in data
    assert "domain_scores" in data
    assert "scenarios" in data
    assert "results" in data
    assert len(data["results"]) == 4  # 4 assessment benchmarks
    assert "benchmark" in data  # metadata section
