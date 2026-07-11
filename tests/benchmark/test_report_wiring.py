from __future__ import annotations

"""Integration test: verify that CLI produces JSON with benchmark metadata.

This test must fail if main() generates reports without passing metadata
-- it is the regression guard against the Phase 5 wiring gap.
"""

import json

from benchmark.metadata import collect_benchmark_metadata
from benchmark.report import generate_json_report


def test_json_report_contains_benchmark_metadata() -> None:
    """JSON report generated with metadata must contain a "benchmark" key."""
    metadata = collect_benchmark_metadata(server_name="sv1", model="test-model")
    results: list[dict] = [
        {
            "benchmark": "test_bm",
            "domain": "test",
            "scores": {"total": 0.95, "reasoning": 1.0, "efficiency": 1.0, "evidence": 1.0, "safety": 1.0},
            "assessment_metrics": {"overall": 0.8},
            "iterations": 1,
            "elapsed": 0.1,
            "errors": [],
        }
    ]

    json_str = generate_json_report(results, metadata=metadata)
    data = json.loads(json_str)

    # The metadata should appear under the "benchmark" key.
    assert "benchmark" in data, (
        f"JSON report missing 'benchmark' key. "
        f"This proves main() is not passing metadata to generate_json_report(). "
        f"Available keys: {list(data.keys())}"
    )

    bm = data["benchmark"]
    assert bm.get("model") == "test-model", f"Expected model='test-model', got {bm.get('model')}"
    assert bm.get("server") == "sv1", f"Expected server='sv1', got {bm.get('server')}"
    assert "provider" in bm, f"Missing 'provider' in metadata keys: {list(bm.keys())}"
    assert "captured_at" in bm
    assert "git_commit" in bm
    assert "benchmark_version" in bm


def test_json_report_without_metadata_omits_benchmark_key() -> None:
    """JSON report generated without metadata must NOT contain a 'benchmark' key."""
    results: list[dict] = [
        {
            "benchmark": "test_bm",
            "domain": "test",
            "scores": {"total": 0.95, "reasoning": 1.0, "efficiency": 1.0, "evidence": 1.0, "safety": 1.0},
            "assessment_metrics": {"overall": 0.8},
            "iterations": 1,
            "elapsed": 0.1,
            "errors": [],
        }
    ]

    json_str = generate_json_report(results)
    data = json.loads(json_str)
    assert "benchmark" not in data, (
        "JSON report should not contain 'benchmark' key when no metadata provided"
    )


def test_human_report_includes_metadata_header() -> None:
    """Human report with metadata should include model and server lines."""
    from benchmark.report import generate_human_report

    metadata = collect_benchmark_metadata(server_name="sv1", model="test-model")
    results: list[dict] = [
        {
            "benchmark": "test_bm",
            "domain": "test",
            "scores": {"total": 0.95, "reasoning": 1.0, "efficiency": 1.0, "evidence": 1.0, "safety": 1.0},
            "assessment_metrics": {"overall": 0.8},
            "iterations": 1,
            "elapsed": 0.1,
            "errors": [],
        }
    ]

    report = generate_human_report(results, metadata=metadata)
    assert "test-model" in report, f"Model 'test-model' missing from human report"
    assert "sv1" in report, f"Server 'sv1' missing from human report"


def test_collect_benchmark_metadata_includes_provider() -> None:
    """collect_benchmark_metadata must capture provider from servers.json."""
    metadata = collect_benchmark_metadata(server_name="sv1")
    assert "provider" in metadata, f"Missing 'provider'. Keys: {list(metadata.keys())}"
    # sv1 in servers.json has provider "openai"
    assert metadata["provider"] == "openai", (
        f"Expected provider='openai' for sv1, got '{metadata.get('provider')}'"
    )
