from __future__ import annotations

"""Unit-level tests for benchmark report functions.

Tests generate_json_report() and generate_human_report() directly.
Does NOT test main() — that is covered by test_main_integration.py.
"""

import json

from benchmark.assessment_evaluator import metrics_to_dict
from benchmark.metadata import collect_benchmark_metadata
from benchmark.report import generate_human_report, generate_json_report


def _sample_result() -> dict:
    return {
        "benchmark": "test_bm",
        "domain": "test",
        "scores": {
            "total": 0.95,
            "reasoning": 1.0,
            "efficiency": 1.0,
            "evidence": 1.0,
            "safety": 1.0,
        },
        "assessment_metrics": {"overall": 0.8},
        "iterations": 1,
        "elapsed": 0.1,
        "errors": [],
    }


def test_json_report_contains_benchmark_metadata() -> None:
    """generate_json_report() with metadata must include a 'benchmark' key."""
    metadata = collect_benchmark_metadata(server_name="sv1", model="test-model")
    json_str = generate_json_report([_sample_result()], metadata=metadata)
    data = json.loads(json_str)

    assert "benchmark" in data, f"Missing 'benchmark' key. Keys: {list(data.keys())}"
    bm = data["benchmark"]
    assert bm.get("model") == "test-model"
    assert bm.get("server") == "sv1"
    assert "provider" in bm
    assert "captured_at" in bm
    assert "git_commit" in bm
    assert "benchmark_version" in bm


def test_json_report_without_metadata_omits_benchmark_key() -> None:
    """generate_json_report() without metadata must NOT include a 'benchmark' key."""
    json_str = generate_json_report([_sample_result()])
    assert "benchmark" not in json.loads(json_str)


def test_human_report_includes_metadata_header() -> None:
    """generate_human_report() with metadata must show model and server."""
    metadata = collect_benchmark_metadata(server_name="sv1", model="test-model")
    report = generate_human_report([_sample_result()], metadata=metadata)
    assert "test-model" in report
    assert "sv1" in report


def test_human_report_shows_assessment_metrics() -> None:
    """Human report should show assessment metrics when present."""
    result = _sample_result()
    result["assessment_metrics"] = metrics_to_dict(
        type(
            "Metrics",
            (),
            {
                "evidence_coverage": 0.8,
                "recommendation_coverage": 0.5,
                "grounding": 0.75,
                "completeness": 1.0,
                "consistency": 1.0,
                "length": 500,
                "overall": 0.81,
            },
        )()
    )
    report = generate_human_report([result])
    assert "ev_cov=0.80" in report
    assert "grd=0.75" in report
    assert "comp=1.00" in report


def test_collect_benchmark_metadata_includes_provider() -> None:
    """collect_benchmark_metadata() must capture provider from servers.json."""
    metadata = collect_benchmark_metadata(server_name="sv1")
    assert metadata.get("provider") == "openai", (
        f"Expected 'openai', got '{metadata.get('provider')}'"
    )
